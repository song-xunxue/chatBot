"""
OpenAICompatProvider SSE 流式解析测试（httpx MockTransport，不触网）
验证 stream_chat 的 delta 解析、[DONE] 终止、非 data 行跳过，以及非流式 chat

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：mock httpx，覆盖 SSE 解析与一次性调用
"""
import json

import pytest
import httpx

from llm.openai_compat import OpenAICompatProvider
from llm.base import Message


def _make_provider():
    """构造一个指向假地址的 provider"""
    p = OpenAICompatProvider(api_key="sk-fake")
    p.base_url = "https://fake.test/v1"
    p.default_model = "fake-model"
    return p


def _sse(*deltas):
    """构造 OpenAI 兼容 SSE 文本：每个 delta 一帧，末尾 data: [DONE]"""
    frames = ["data: " + json.dumps({"choices": [{"delta": d, "index": 0}]}) for d in deltas]
    frames.append("data: [DONE]")
    return "\n\n".join(frames) + "\n\n"


@pytest.fixture
def mock_httpx(monkeypatch):
    """让 httpx.AsyncClient 走 MockTransport，返回指定响应体"""
    def _install(response_text, status=200, content_type="text/event-stream"):
        def handler(request):
            return httpx.Response(status, text=response_text,
                                  headers={"content-type": content_type})
        transport = httpx.MockTransport(handler)
        real = httpx.AsyncClient

        def patched(*args, **kwargs):
            kwargs["transport"] = transport
            return real(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", patched)

    return _install


async def test_stream_chat_parses_deltas_skips_empty(mock_httpx):
    mock_httpx(_sse({"content": "Hel"}, {"content": "lo"}, {"content": ""}))
    out = [d.text async for d in _make_provider().stream_chat([Message(role="user", content="hi")])]
    assert out == ["Hel", "lo"]  # 空 content 帧被跳过


async def test_stream_chat_stops_at_done(mock_httpx):
    mock_httpx(_sse({"content": "A"}, {"content": "B"}))
    out = [d.text async for d in _make_provider().stream_chat([Message(role="user", content="x")])]
    assert out == ["A", "B"]


async def test_stream_chat_skips_non_data_lines(mock_httpx):
    # 注释行(:) 与 event: 行应被跳过，只解析 data: 行
    sse = (
        ":keepalive\n\n"
        "event: ping\n\n"
        "data: " + json.dumps({"choices": [{"delta": {"content": "X"}}]}) + "\n\n"
        "data: [DONE]\n\n"
    )
    mock_httpx(sse)
    out = [d.text async for d in _make_provider().stream_chat([Message(role="user", content="x")])]
    assert out == ["X"]


async def test_chat_non_stream_parses_json(mock_httpx):
    payload = {"choices": [{"message": {"content": "完整回复"}, "finish_reason": "stop"}]}
    mock_httpx(json.dumps(payload), content_type="application/json")
    resp = await _make_provider().chat([Message(role="user", content="hi")])
    assert resp.text == "完整回复"
    assert resp.finish_reason == "stop"
