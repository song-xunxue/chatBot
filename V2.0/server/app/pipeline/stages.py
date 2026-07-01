"""
管道各阶段(stages)
M2 实现:load_history / persona_inject / memory_retrieve / mood_inject / build_messages /
         llm_stream / save / mood_update / memory_write。
适配 V2.0:block 三层 chat_store(get_history(max_messages)/append_message(sender=)) + mood 服务。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 stages 到 V2.0;load_history/save 适配 block chat_store 签名;
     新增 stage_mood_inject(before_llm 注入 prompt_hint)/ stage_mood_update(after_llm 情感更新)

2026-06-28
变更说明：
  1. M3 stage_save 把 ai 消息 mid 存入 ctx.reply_mid;新增 stage_score(save 后对 ai 回复
     自动 LLM 评分 + 心情补偿 + 写 score 四元组 + 正负样本归类)
"""
from typing import AsyncIterator
import asyncio
import logging
import time

from redis.asyncio import Redis

from pipeline.context import MessageContext
from llm.base import Message
from llm.registry import get_provider
from storage import chat_store
from core.config import settings

logger = logging.getLogger(__name__)

# 在途后台记忆编码任务强引用集合:防止 asyncio.create_task 的 Task 被 GC 在完成前取消
_BG_TASKS: set[asyncio.Task] = set()


async def stage_load_history(ctx: MessageContext, redis: Redis) -> None:
    """阶段①:从 Redis 取最近对话历史(Working 层),取最近 max_messages 条(block 三层,get_history 只读真实键)"""
    ctx.history = await chat_store.get_history(redis, ctx.object_id,
                                               max_messages=settings.memory_working_window)


async def stage_persona_inject(ctx: MessageContext, redis) -> None:
    """阶段②:人设注入(加载 PersonaCard,渲染 system_prompt)。
    从人设系统按 object_id 解析;缺失则用默认人设。system_prompt 已被上层显式设置时不覆盖。"""
    from persona.store import get_object_persona_id, get_persona, get_default_persona
    from persona.renderer import render_system_prompt
    pid = ctx.persona_id or await get_object_persona_id(redis, ctx.object_id)
    card = await get_persona(redis, pid)
    if card is None:
        card = await get_default_persona(redis)  # 兜底默认人设
    ctx.persona_card = card
    ctx.persona_id = card.id if card else pid
    # 应用人设绑定的 provider/model:仅当 provider 非空才应用(空=继承全局 chat_provider);
    # model 必须跟 provider 一起应用,否则孤立的 model 名(如旧数据 "glm-5.2")会打到别的 provider 报错
    if card and card.model and card.model.provider:
        ctx.provider_name = card.model.provider
        if card.model.model:
            ctx.model = card.model.model
    if not ctx.system_prompt:
        ctx.system_prompt = render_system_prompt(card, card.dynamic_state if card else None)


async def stage_memory_retrieve(ctx: MessageContext, redis) -> None:
    """阶段②.5:记忆检索(插入 persona_inject 与 mood_inject 之间)
    从四级记忆召回相关条目并组装 memory_block,拼入 system_prompt 尾部。
    memory_enabled=False 时跳过(降级无记忆)。"""
    if not settings.memory_enabled:
        return
    from memory.coordinator import get_memory_coordinator
    coord = await get_memory_coordinator()
    result = await coord.retrieve(ctx.object_id, ctx.user_text,
                                  top_k=settings.memory_retrieve_topk,
                                  working_messages=ctx.history)
    ctx.recall_result = result
    ctx.memory_block = coord.render(result)
    ctx.memory_meta = {"hit_mids": result.hit_mids}


async def stage_mood_inject(ctx: MessageContext, redis) -> None:
    """阶段②.6:心情注入(在调 LLM 前)。
    读当前 mood → 查档位 → 把档位 prompt_hint + 颜文字追加到 system_prompt(影响回复语气),
    并写 ctx.plugin_meta 供 QQ 回复/面板展示。对应 docs/03 §7.1。"""
    from mood import service
    mood = await service.get_mood(redis, ctx.object_id)
    ctx.mood_value = mood
    kinds = await service.list_kinds(redis)
    kind = service.lookup_kind(mood, kinds)
    if kind:
        if ctx.system_prompt:
            ctx.system_prompt += (
                f"\n[当前心情:{kind['label']} {kind['kaomoji']},{kind['prompt_hint']}]"
            )
        ctx.plugin_meta["mood"] = kind["label"]
        ctx.plugin_meta["mood_kaomoji"] = kind["kaomoji"]


async def stage_build_messages(ctx: MessageContext) -> list[Message]:
    """阶段③:拼装发送给 LLM 的消息列表(system[+memory_block] + 历史 + 本次用户消息)。
    memory_block 拼到 system_prompt 尾部(规避部分 provider 双 system 兼容问题)。"""
    messages: list[Message] = []
    if ctx.system_prompt:
        content = ctx.system_prompt
        if ctx.memory_block:
            content = f"{ctx.system_prompt}\n\n{ctx.memory_block}"
        messages.append(Message(role="system", content=content))
    messages.extend(ctx.history)
    messages.append(Message(role="user", content=ctx.user_text))
    return messages


async def stage_llm_stream(ctx: MessageContext) -> AsyncIterator[str]:
    """阶段④:流式调用 LLM,异步生成器逐 token 产出文本。
    QQ 场景不逐 token 发(由 webhook 累积为完整回复再下发);流式接口保留供 M6 outputpro 分段。"""
    provider = get_provider(ctx.provider_name)
    messages = await stage_build_messages(ctx)
    async for delta in provider.stream_chat(messages, model=ctx.model):
        yield delta.text


async def stage_save(ctx: MessageContext, redis: Redis) -> None:
    """阶段④:把本次用户消息 + AI 回复写入历史(block 三层,落当前 open block)。
    V2.0 sender 用 user/ai(弃 V1.0 role),source=live。user/ai 用递增 ts 保证时序(user 先,ai 后)。
    ai 消息 mid 存 ctx.reply_mid,供 stage_score 评分定位。"""
    base_ts = ctx.created_ts or int(time.time() * 1000)
    await chat_store.append_message(redis, ctx.object_id,
                                    sender="user", content=ctx.user_text,
                                    source="live", ts=base_ts)
    ctx.reply_mid = await chat_store.append_message(redis, ctx.object_id,
                                                    sender="ai", content=ctx.reply_text,
                                                    source="live", ts=base_ts + 1)


async def stage_score(ctx: MessageContext, redis: Redis) -> None:
    """阶段④.5:对本次 ai 回复自动 LLM 评分(对照人设)+ 心情补偿 + 写 score 四元组 + 样本归类。
    在 stage_save 后执行(用 ctx.reply_mid 定位);score_enabled=False 或评分失败则跳过(不阻塞)。
    对应 docs/01 §4 / docs/02 §5 / docs/03 §5。评分用对话同款 provider(ctx.provider_name)。"""
    if not settings.score_enabled:
        return
    if not ctx.reply_mid or not ctx.reply_text:
        return
    from score import service as score_service
    try:
        await score_service.score_reply(
            redis, ctx.object_id, ctx.reply_text, ctx.persona_card, ctx.reply_mid,
            mood_value=ctx.mood_value, provider_name=ctx.provider_name,
        )
    except Exception:
        logger.exception("score stage failed")   # 评分失败不阻塞主流程与记忆编码


async def stage_tool_loop(ctx: MessageContext, redis: Redis) -> str | None:
    """阶段③':有注册工具时走 tool-loop(LLM function calling 决策调工具→执行→再推理),
    返回最终回复文本;tool_loop_enable=False 或无注册工具时返回 None(pipeline 降级 stream_chat)。
    对应 docs/01 §6。非流式(QQ 累积完整回复);与 stream 互斥(有工具走 tool-loop,否则 stream)。"""
    if not settings.tool_loop_enable:
        return None
    from tools import get_tool_registry
    from tools.base import ToolContext
    from pipeline.tool_loop import run_tool_loop
    registry = get_tool_registry()
    if not registry.all():
        return None
    provider = get_provider(ctx.provider_name)
    tctx = ToolContext(redis, object_id=ctx.object_id)
    try:
        return await run_tool_loop(provider, ctx.system_prompt, ctx.user_text,
                                   ctx.history, registry, tctx,
                                   model=ctx.model, max_iterations=settings.tool_loop_max_iterations)
    except Exception as e:
        # tool-loop 失败(provider 限流/超时/超上限):降级返回 None → runner 走 stage_llm_stream
        # 兜底保证用户仍收到正常回复(无工具),绝不把错误堆栈当回复发给 QQ 用户
        logger.warning("tool-loop 失败(provider=%s),降级 stream_chat: %s",
                       ctx.provider_name, e)
        return None


async def stage_mood_update(ctx: MessageContext, redis) -> None:
    """阶段④.5:心情情感更新(LLM 产出后)。
    按回复文本关键词情感更新 mood(正向词↑step/负向词↓step)。对应 docs/03 §4.1。
    复用 V1.0 mood_dynamic 行为(用 reply_text);后续可扩展 user_text 共情。"""
    from mood import service
    if ctx.reply_text:
        await service.apply_emotion(redis, ctx.object_id, ctx.reply_text)


async def stage_memory_write(ctx: MessageContext, redis: Redis) -> None:
    """阶段⑤:记忆编码(流结束后异步触发,失败不阻塞回复)
    触发 coordinator.on_turn_complete:Episodic 摘要/反思 + Long-term 事实抽取。
    memory_enabled=False 时跳过。"""
    if not settings.memory_enabled:
        return
    from memory.coordinator import get_memory_coordinator
    coord = await get_memory_coordinator()
    task = asyncio.create_task(_safe_on_turn(coord, ctx))
    _BG_TASKS.add(task)                          # 持强引用,防 GC 提前取消
    task.add_done_callback(_BG_TASKS.discard)    # 完成后自动移除,避免集合无限增长


async def _safe_on_turn(coord, ctx) -> None:
    """包装 on_turn_complete,吞掉所有异常避免未捕获告警"""
    try:
        await coord.on_turn_complete(ctx)
    except Exception:
        logger.exception("memory write failed")
