"""
管道 runner：编排各阶段顺序执行
流式入口 run_stream：load_history → persona_inject → llm_stream(边产边推) → save。
对应 docs/02 §4.2 管道顺序（M2 仅实现核心子集，记忆检索/插件钩子待 M3/M4 插入）。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.2 创建 run_stream 流式 runner：返回 token 异步生成器，调用方边收边推 WebSocket
"""
from typing import AsyncIterator

from pipeline.context import MessageContext
from pipeline.stages import (
    stage_load_history, stage_persona_inject, stage_llm_stream, stage_save,
)
from storage.redis_client import get_redis


async def run_stream(ctx: MessageContext) -> AsyncIterator[str]:
    """流式执行管道：产出 token 异步生成器。

    顺序：①取历史 → ②人设注入(占位) → ③流式调 LLM(边产边推) → ④存历史
    调用方（ws.py）迭代本生成器，每拿到一个 token 就推 ai_chunk 给客户端。
    """
    redis = await get_redis()
    # ①取历史
    await stage_load_history(ctx, redis)
    # ②人设注入（M2 占位）
    await stage_persona_inject(ctx)
    # ③流式调 LLM：边产边推，同时累积完整回复
    full_reply: list[str] = []
    async for token in stage_llm_stream(ctx):
        full_reply.append(token)
        yield token  # 推给调用方（WS → 客户端）
    ctx.reply_text = "".join(full_reply)
    # ④存历史（用户消息 + 完整回复）
    await stage_save(ctx, redis)
