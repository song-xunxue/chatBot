"""
pipeline tool-loop 集成单测:有注册工具走 tool-loop(产最终回复)/ 无工具降级 stream。
用 fresh ToolRegistry(monkeypatch get_tool_registry,不污染全局)+ mock provider(chat_with_tools)。

作者: 李文煜
日期: 2026-06-28
"""
import json

import storage.redis_client as redis_client
from core.config import settings
from llm.base import LLMResponse
from tools.base import Tool, ToolRegistry
from pipeline.context import MessageContext
from pipeline.runner import run_stream
from mood import service as mood_service


class _NoteTool(Tool):
    name = "note"
    description = "记录一条信息"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, args, ctx):
        return f"已记录{args.get('text', '')}"


async def test_pipeline_uses_tool_loop_when_tools_registered(fake_redis, make_provider, monkeypatch):
    """有工具 + tool_loop 开 → run_stream 走 tool-loop,ctx.reply_text 为最终回复"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    monkeypatch.setattr(settings, "tool_loop_enable", True)    # 覆盖 autouse 的 _disable_tool_loop
    fresh = ToolRegistry()
    fresh.register(_NoteTool())
    monkeypatch.setattr("tools.get_tool_registry", lambda: fresh)
    p = make_provider([
        LLMResponse(text="", tool_calls=[{
            "id": "c1", "name": "note",
            "arguments": json.dumps({"text": "猫"}, ensure_ascii=False),
        }]),
        LLMResponse(text="好的我记下了"),
    ])
    monkeypatch.setattr("pipeline.stages.get_provider", lambda n: p)

    ctx = MessageContext(object_id="u1", user_text="记一下我喜欢猫")
    tokens = [t async for t in run_stream(ctx)]
    assert ctx.reply_text == "好的我记下了"
    assert "好的我记下了" in tokens    # tool-loop 一次性 yield 完整回复


async def test_pipeline_falls_back_to_stream_when_no_tools(fake_redis, make_provider, monkeypatch):
    """无工具(空 registry)→ stage_tool_loop 返 None → 降级 stream_chat"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    monkeypatch.setattr(settings, "tool_loop_enable", True)
    monkeypatch.setattr("tools.get_tool_registry", lambda: ToolRegistry())   # 空
    p = make_provider([LLMResponse(text="stream-reply")])
    monkeypatch.setattr("pipeline.stages.get_provider", lambda n: p)

    ctx = MessageContext(object_id="u1", user_text="嗨")
    async for _ in run_stream(ctx):
        pass
    assert ctx.reply_text == "stream-reply"


async def test_pipeline_tool_loop_disabled_falls_back(fake_redis, make_provider, monkeypatch):
    """tool_loop_enable=False(autouse 默认)→ 即使有工具也走 stream"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    # tool_loop_enable 保持 autouse 的 False,不覆盖
    fresh = ToolRegistry()
    fresh.register(_NoteTool())
    monkeypatch.setattr("tools.get_tool_registry", lambda: fresh)
    p = make_provider([LLMResponse(text="stream-reply")])
    monkeypatch.setattr("pipeline.stages.get_provider", lambda n: p)

    ctx = MessageContext(object_id="u1", user_text="嗨")
    async for _ in run_stream(ctx):
        pass
    assert ctx.reply_text == "stream-reply"
