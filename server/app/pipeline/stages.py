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

from redis.asyncio import Redis

from pipeline.context import MessageContext
from llm.base import Message
from llm.registry import get_provider
from storage import chat_store


async def stage_load_history(ctx: MessageContext, redis: Redis) -> None:
    """阶段①：从 Redis 取最近对话历史，填入 ctx.history"""
    ctx.history = await chat_store.get_history(redis, ctx.object_id, limit=20)


async def stage_persona_inject(ctx: MessageContext) -> None:
    """阶段②：人设注入（拼 system_prompt）。
    M2 占位：用固定通用 prompt；M3 将从人设系统加载 name/personality/scenario 等拼装。
    """
    if not ctx.system_prompt:
        ctx.system_prompt = "你是一个友善的聊天助手，请自然、简洁地与用户对话。"


async def stage_build_messages(ctx: MessageContext) -> list[Message]:
    """阶段③：拼装发送给 LLM 的消息列表（system + 历史 + 本次用户消息）"""
    messages: list[Message] = []
    if ctx.system_prompt:
        messages.append(Message(role="system", content=ctx.system_prompt))
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
    """阶段⑤：把本次用户消息 + AI 回复写入历史（记忆系统写入 M3 扩展）"""
    await chat_store.append_message(redis, ctx.object_id, "user", ctx.user_text)
    await chat_store.append_message(redis, ctx.object_id, "assistant", ctx.reply_text)
