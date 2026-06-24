"""
管道 runner：编排各阶段顺序执行
流式入口 run_stream：load_history → persona_inject → memory_retrieve → 插件钩子 → llm_stream → save。
对应 docs/02 §4.2 管道顺序；M4 在 4 个点接入插件钩子（on_message_in/before_llm/after_llm/message_out）。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.2 创建 run_stream 流式 runner：返回 token 异步生成器，调用方边收边推 WebSocket

2026-06-24
变更说明：
  1. M4.1 接入插件钩子：on_message_in(可丢弃)/on_before_llm(可跳过LLM)/on_after_llm(富内容)/on_message_out(增强)
     bus 未初始化(get_event_bus()==None)时跳过全部钩子，保持 M2/M3 向后兼容
  2. M4.1-review 修正钩子顺序与 STOP 语义：on_message_out 移到 stage_save 之前（其改写入历史）；
     on_after_llm 仅在 LLM 真实产出时触发（skip_llm 时不触发），其 STOP 跳过 on_message_out
"""
from typing import AsyncIterator

from pipeline.context import MessageContext
from pipeline.stages import (
    stage_load_history, stage_persona_inject, stage_memory_retrieve,
    stage_llm_stream, stage_save, stage_memory_write,
)
from storage.redis_client import get_redis
from plugins import get_event_bus
from plugins.base import (
    ON_MESSAGE_IN, ON_BEFORE_LLM, ON_AFTER_LLM, ON_MESSAGE_OUT, HookResult,
)


async def run_stream(ctx: MessageContext) -> AsyncIterator[str]:
    """流式执行管道：产出 token 异步生成器。

    顺序：
      on_message_in → ①取历史 → ②人设注入 → ②.5记忆检索
      → on_before_llm → ③流式调 LLM(边产边推) → on_after_llm → on_message_out → ④存历史 → ⑤记忆编码
    调用方（ws.py）迭代本生成器，每拿到一个 token 就推 ai_chunk 给客户端。
    插件钩子点：on_message_in(STOP 丢弃)、on_before_llm(STOP 跳过 LLM)、
      on_after_llm(仅 LLM 真实产出时触发；STOP 跳过回复增强)、on_message_out(置于 stage_save 前，改写入历史)。
    """
    redis = await get_redis()
    bus = get_event_bus()
    # on_message_in：用户消息到达；STOP 则丢弃整条消息（不进后续阶段）
    if bus is not None and await bus.fire(ON_MESSAGE_IN, ctx) == HookResult.STOP:
        return
    # ①取历史
    await stage_load_history(ctx, redis)
    # ②人设注入（M3：真实人设加载，替换 M2 占位）
    await stage_persona_inject(ctx, redis)
    # ②.5记忆检索（M3：召回四层记忆，组装 memory_block 拼入 system_prompt）
    await stage_memory_retrieve(ctx, redis)
    # on_before_llm：prompt 拼装后、调 LLM 前；STOP 则跳过 LLM（插件可自产 ctx.reply_text）
    skip_llm = bus is not None and await bus.fire(ON_BEFORE_LLM, ctx) == HookResult.STOP
    # ③流式调 LLM：边产边推，同时累积完整回复
    full_reply: list[str] = []
    if not skip_llm:
        async for token in stage_llm_stream(ctx):
            full_reply.append(token)
            yield token  # 推给调用方（WS → 客户端）
        ctx.reply_text = "".join(full_reply)
    # on_after_llm：LLM 真实产出后触发（skip_llm 时不触发）；TTS/图像/表情包收集到 ctx.rich；
    # STOP 则跳过回复增强(on_message_out)
    skip_out = skip_llm
    if bus is not None and not skip_llm:
        if await bus.fire(ON_AFTER_LLM, ctx) == HookResult.STOP:
            skip_out = True
    # on_message_out：回复增强/多段合并；置于 stage_save 之前，使其对 reply_text 的改写入历史
    if bus is not None and not skip_out:
        await bus.fire(ON_MESSAGE_OUT, ctx)
    # ④存历史（用户消息 + 最终回复；含 on_after_llm/on_message_out 的改写）
    await stage_save(ctx, redis)
    # ⑤记忆编码（异步触发：摘要/反思/事实抽取，不阻塞 WS 回复）
    await stage_memory_write(ctx, redis)
