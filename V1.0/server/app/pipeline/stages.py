"""
管道各阶段（stages）
M2 实现：load_history(取历史) / persona_inject(占位) / build_messages(拼消息) /
         llm_stream(流式调 LLM) / save(存历史)
占位（M3/M4 填）：人设系统化、记忆检索、插件钩子 —— 当前 persona_inject 用固定 prompt。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.2 创建各阶段函数；persona/memory/plugins 留接口待 M3/M4 扩展
"""
from typing import AsyncIterator
import asyncio
import logging

from redis.asyncio import Redis

from pipeline.context import MessageContext
from llm.base import Message
from llm.registry import get_provider
from storage import chat_store
from core.config import settings

logger = logging.getLogger(__name__)

# 在途后台记忆编码任务强引用集合：防止 asyncio.create_task 的 Task 被 GC 在完成前取消
_BG_TASKS: set[asyncio.Task] = set()


async def stage_load_history(ctx: MessageContext, redis: Redis) -> None:
    """阶段①：从 Redis 取最近对话历史（Working 层），窗口大小由 settings.memory_working_window 控制"""
    ctx.history = await chat_store.get_history(redis, ctx.object_id, limit=settings.memory_working_window)


async def stage_persona_inject(ctx: MessageContext, redis) -> None:
    """阶段②：人设注入（加载真实人设，渲染 system_prompt）。
    M3：从人设系统按 object_id 解析 PersonaCard 并渲染；缺失则用默认人设。
    system_prompt 已被上层显式设置时不覆盖（保留"非空不覆盖"语义）。
    """
    from persona.store import get_object_persona_id, get_persona, get_default_persona
    from persona.renderer import render_system_prompt
    pid = ctx.persona_id or await get_object_persona_id(redis, ctx.object_id)
    card = await get_persona(redis, pid)
    if card is None:
        card = await get_default_persona(redis)  # 兜底默认人设
    ctx.persona_card = card
    ctx.persona_id = card.id if card else pid
    if not ctx.system_prompt:
        ctx.system_prompt = render_system_prompt(card, card.dynamic_state if card else None)


async def stage_memory_retrieve(ctx: MessageContext, redis) -> None:
    """阶段②.5：记忆检索（插入 persona_inject 与 llm_stream 之间）
    从四级记忆召回相关条目并组装 memory_block，拼入 system_prompt 尾部。
    memory_enabled=False 时跳过（降级为 M2 行为）。"""
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


async def stage_build_messages(ctx: MessageContext) -> list[Message]:
    """阶段③：拼装发送给 LLM 的消息列表（system[+memory_block] + 历史 + 本次用户消息）
    M3：memory_block 拼到 system_prompt 尾部（规避部分 provider 双 system 兼容问题）"""
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
    """阶段④：流式调用 LLM，异步生成器逐 token 产出文本（供 runner 边产边推 WS）"""
    provider = get_provider(ctx.provider_name)
    messages = await stage_build_messages(ctx)
    async for delta in provider.stream_chat(messages, model=ctx.model):
        yield delta.text


async def stage_save(ctx: MessageContext, redis: Redis) -> None:
    """阶段④：把本次用户消息 + AI 回复写入历史（Working 层）"""
    await chat_store.append_message(redis, ctx.object_id, "user", ctx.user_text, ts=ctx.created_ts)
    await chat_store.append_message(redis, ctx.object_id, "assistant", ctx.reply_text, ts=ctx.created_ts)


async def stage_memory_write(ctx: MessageContext, redis: Redis) -> None:
    """阶段⑤：记忆编码（流结束后异步触发，失败不阻塞回复）
    触发 coordinator.on_turn_complete：Episodic 摘要/反思 + Long-term 事实抽取。
    memory_enabled=False 时跳过（降级 M2）。"""
    if not settings.memory_enabled:
        return
    from memory.coordinator import get_memory_coordinator
    coord = await get_memory_coordinator()
    task = asyncio.create_task(_safe_on_turn(coord, ctx))
    _BG_TASKS.add(task)                          # 持强引用，防 GC 提前取消
    task.add_done_callback(_BG_TASKS.discard)    # 完成后自动移除，避免集合无限增长


async def _safe_on_turn(coord, ctx) -> None:
    """包装 on_turn_complete，吞掉所有异常避免未捕获告警"""
    try:
        await coord.on_turn_complete(ctx)
    except Exception:
        logger.exception("memory write failed")
