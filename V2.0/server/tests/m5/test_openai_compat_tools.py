"""
openai_compat chat_with_tools 单测:解析 tool_calls(含 arguments JSON)/ 无 tools 返回纯文本。
用 mock httpx(不真调 GLM),验 function calling 响应解析。

作者: 李文煜
日期: 2026-06-28
"""
import json

import httpx

from llm.glm import GLMProvider


def _mock_client(json_payload):
    """构造 httpx.AsyncClient 替身:post 返回固定 json payload"""
    class _Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return json_payload
    class _Client:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None):
            return _Resp()
    return _Client


async def test_chat_with_tools_parses_tool_calls(monkeypatch):
    payload = {"choices": [{"message": {
        "content": "",
        "tool_calls": [{"id": "c1", "function": {"name": "note",
                                                  "arguments": '{"text": "x"}'}}],
    }, "finish_reason": "tool_calls"}]}
    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(payload))
    p = GLMProvider(api_key="k")
    resp = await p.chat_with_tools(
        [{"role": "user", "content": "x"}],
        tools=[{"type": "function", "function": {"name": "note"}}])
    assert resp.tool_calls[0]["name"] == "note"
    assert resp.tool_calls[0]["id"] == "c1"
    assert json.loads(resp.tool_calls[0]["arguments"])["text"] == "x"
    assert resp.finish_reason == "tool_calls"


async def test_chat_with_tools_no_tools_text(monkeypatch):
    payload = {"choices": [{"message": {"content": "你好"}, "finish_reason": "stop"}]}
    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(payload))
    p = GLMProvider(api_key="k")
    resp = await p.chat_with_tools([{"role": "user", "content": "hi"}], tools=None)
    assert resp.text == "你好"
    assert resp.tool_calls == []


async def test_chat_with_tools_empty_tool_calls(monkeypatch):
    """有 tools 但 LLM 未调(空 tool_calls)→ tool_calls=[]"""
    payload = {"choices": [{"message": {"content": "直接回答"}, "finish_reason": "stop"}]}
    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(payload))
    p = GLMProvider(api_key="k")
    resp = await p.chat_with_tools(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "note"}}])
    assert resp.text == "直接回答"
    assert resp.tool_calls == []
