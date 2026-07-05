"""
发私聊消息(httpx MockTransport)测试

作者: 李文煜
日期: 2026-06-25
"""
import json
import time

import httpx
import pytest

import qq.api_client as qq_api
from qq.api_client import send_c2c_message
from qq.auth import _TOKEN_KEY


async def _seed_token(fake_redis):
    """预置有效 token 缓存,避免 send 时去换 token(隔离发消息逻辑)"""
    await fake_redis.set(_TOKEN_KEY, json.dumps({"value": "tok-123", "expires_at": time.time() + 9999}))


async def test_send_c2c_passive_reply(fake_redis, api_client):
    """被动回复:带 msg_id,Authorization 注入,路径含 openid"""
    await _seed_token(fake_redis)
    resp = await send_c2c_message("OID-1", "hello", msg_id="MID-1")
    assert resp["id"] == "MSG-001"
    req = api_client["requests"][-1]
    assert "/v2/users/OID-1/messages" in str(req.url)
    assert req.headers["Authorization"] == "QQBot tok-123"
    payload = json.loads(req.content)
    assert payload["msg_type"] == 0
    assert payload["msg_id"] == "MID-1"
    assert payload["msg_seq"] == 1
    assert payload["content"] == "hello"


async def test_send_c2c_active_message_no_msg_id(fake_redis, api_client):
    """主动消息(无 msg_id):payload 不含 msg_id(M8 代人聊天用,耗月配额)"""
    await _seed_token(fake_redis)
    await send_c2c_message("OID-1", "hi")
    payload = json.loads(api_client["requests"][-1].content)
    assert "msg_id" not in payload


async def test_send_c2c_raises_on_http_error(fake_redis, api_client, monkeypatch):
    """QQ 返错误(如超频 22009)→ raise_for_status 抛 HTTPStatusError"""
    await _seed_token(fake_redis)

    class _BadResp:
        status_code = 500

        def raise_for_status(self):
            raise httpx.HTTPStatusError("msg limit exceed", request=None, response=self)

        def json(self):
            return {"code": 22009, "message": "msg limit exceed"}

    async def _bad_post(*args, **kwargs):
        return _BadResp()

    monkeypatch.setattr(qq_api._client, "post", _bad_post)
    with pytest.raises(httpx.HTTPStatusError):
        await send_c2c_message("OID-1", "x", msg_id="M")


async def test_send_sanitizes_machine_output_by_default(fake_redis, api_client):
    """出站守卫(架构 #3,#4 下沉到 send):默认 human_authored=False → 机器产出的错误文本过守卫降级"""
    await _seed_token(fake_redis)
    bad = "Client error '429 Too Many Requests' for url 'https://api.deepseek.com/x'"
    await send_c2c_message("OID", bad, msg_id="M")
    payload = json.loads(api_client["requests"][-1].content)
    assert "429" not in payload["content"]
    assert "deepseek" not in payload["content"]


async def test_send_human_authored_bypasses_guard(fake_redis, api_client):
    """human_authored=True(代答):admin 文本原样发,即使含错误模式关键词也不降级"""
    await _seed_token(fake_redis)
    # 这段文本若过守卫会被降级(命中 Client error '429 / api.deepseek.com)
    text = "调试日志: Client error '429 Too Many Requests' for url 'https://api.deepseek.com/x'"
    await send_c2c_message("OID", text, msg_id="M", human_authored=True)
    payload = json.loads(api_client["requests"][-1].content)
    assert payload["content"] == text   # 原样,未被守卫改动
