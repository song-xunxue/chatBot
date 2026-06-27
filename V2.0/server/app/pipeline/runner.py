"""
管道 runner:编排各阶段顺序执行
流式入口 run_stream:
  on_message_in → load_history → persona_inject → memory_retrieve → mood_inject
  → on_before_llm → llm_stream(边产边推) → on_after_llm → mood_update → on_message_out
  → save → memory_write

V2.0 适配(M2):mood 融入架构后 stage_mood_inject/stage_mood_update 作为独立阶段
(非插件钩子)。bus 未初始化时跳过插件钩子,保持降级兼容。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 runner 到 V2.0;编排插入 stage_mood_inject(memory_retrieve 后)/
     stage_mood_update(on_after_llm 后)
"""
from typing import AsyncIterator

from pipeline.context import MessageContext
from pipeline.stages import (
    stage_load_history, stage_persona_inject, stage_memory_retrieve,
    stage_mood_inject, stage_llm_stream, stage_save, stage_score, stage_mood_update,
    stage_memory_write,
)
from storage.redis_client import get_redis
from plugins import get_event_bus
from plugins.base import (
    ON_MESSAGE_IN, ON_BEFORE_LLM, ON_AFTER_LLM, ON_MESSAGE_OUT, HookResult,
)


async def run_stream(ctx: MessageContext) -> AsyncIterator[str]:
    """流式执行管道:产出 token 异步生成器。

    顺序:
      on_message_in → ①取历史 → ②人设注入 → ②.5记忆检索 → ②.6心情注入
      → on_before_llm → ③流式调 LLM(边产边推) → on_after_llm → ②.6'心情更新
      → on_message_out → ④存历史 → ④.5评分(M3) → ⑤记忆编码
    QQ 场景调用方(webhook)迭代本生成器累积为完整回复,再一次性被动下发(不逐 token 发)。
    插件钩子(M6 加载插件后才生效):on_message_in(STOP 丢弃)/on_before_llm(STOP 跳过 LLM)/
      on_after_llm(仅 LLM 真实产出时触发;STOP 跳过回复增强)/on_message_out(置于 save 前)。
    """
    redis = await get_redis()
    bus = get_event_bus()
    # on_message_in:用户消息到达;STOP 则丢弃整条消息(不进后续阶段)
    if bus is not None and await bus.fire(ON_MESSAGE_IN, ctx) == HookResult.STOP:
        return
    # ①取历史
    await stage_load_history(ctx, redis)
    # ②人设注入
    await stage_persona_inject(ctx, redis)
    # ②.5记忆检索
    await stage_memory_retrieve(ctx, redis)
    # ②.6心情注入(prompt_hint 追加到 system_prompt)
    await stage_mood_inject(ctx, redis)
    # on_before_llm:prompt 拼装后、调 LLM 前;STOP 则跳过 LLM(插件可自产 ctx.reply_text)
    skip_llm = bus is not None and await bus.fire(ON_BEFORE_LLM, ctx) == HookResult.STOP
    # ③流式调 LLM:边产边推,同时累积完整回复
    full_reply: list[str] = []
    if not skip_llm:
        async for token in stage_llm_stream(ctx):
            full_reply.append(token)
            yield token  # 推给调用方(QQ 场景 webhook 累积)
        ctx.reply_text = "".join(full_reply)
    # on_after_llm:LLM 真实产出后触发(skip_llm 时不触发);STOP 则跳过回复增强(on_message_out)
    skip_out = skip_llm
    if bus is not None and not skip_llm:
        if await bus.fire(ON_AFTER_LLM, ctx) == HookResult.STOP:
            skip_out = True
    # ②.6'心情情感更新(按回复关键词更新 mood)
    await stage_mood_update(ctx, redis)
    # on_message_out:回复增强/多段合并;置于 stage_save 之前,使其对 reply_text 的改写入历史
    if bus is not None and not skip_out:
        await bus.fire(ON_MESSAGE_OUT, ctx)
    # ④存历史(用户消息 + 最终回复,落当前 open block)
    await stage_save(ctx, redis)
    # ④.5评分(M3):对 ai 回复自动 LLM 评分 + 心情补偿 + 写 score 四元组 + 样本归类(失败不阻塞)
    await stage_score(ctx, redis)
    # ⑤记忆编码(异步触发:摘要/反思/事实抽取,不阻塞回复)
    await stage_memory_write(ctx, redis)
