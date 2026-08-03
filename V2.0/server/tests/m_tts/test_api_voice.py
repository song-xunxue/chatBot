"""
QQ 上传/发语音 api_client 单测(M-tts,2026-08-04)
覆盖:upload_c2c_file(POST /v2/users/{openid}/files,file_type=3 + base64 + srv_send_msg=false)
+ send_c2c_voice(POST messages,msg_type=7 + media.file_info + msg_id/msg_seq,主动消息无 msg_id)。
mock httpx(MockTransport 路由 files/messages)+ token(get_access_token 直 patch)。

作者: 李文煜
日期: 2026-08-04
"""
import json

import httpx

import qq.api_client as api


def _setup(monkeypatch, handler):
    """注入 MockTransport 客户端(路由 files/messages)+ 假 token,返回 captured"""
    captured = {}

    def h(request):
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return handler(request)

    monkeypatch.setattr(api, "_client", httpx.AsyncClient(transport=httpx.MockTransport(h)))

    async def fake_token():
        return "tok-fake"

    monkeypatch.setattr(api, "get_access_token", fake_token)
    return captured


async def test_upload_c2c_file(monkeypatch):
    """上传:POST .../files,file_type=3 + base64 + srv_send_msg=false,返回 file_info"""
    captured = _setup(monkeypatch, lambda r: httpx.Response(
        200, json={"file_uuid": "FU-1", "file_info": "FI-xxx", "ttl": 300}))
    out = await api.upload_c2c_file("oid1", api.FILE_TYPE_VOICE, "BASE64DATA")
    assert out["file_info"] == "FI-xxx"
    assert captured["url"].endswith("/v2/users/oid1/files")
    assert captured["auth"] == "QQBot tok-fake"
    assert captured["body"]["file_type"] == 3
    assert captured["body"]["file_data"] == "BASE64DATA"
    assert captured["body"]["srv_send_msg"] is False


async def test_send_c2c_voice_passive(monkeypatch):
    """被动回复:msg_type=7 + media.file_info + msg_id + msg_seq,纯语音无 content"""
    captured = _setup(monkeypatch, lambda r: httpx.Response(
        200, json={"id": "MSG-1", "timestamp": 1700000000}))
    out = await api.send_c2c_voice("oid1", "FI-xxx", msg_id="MID", msg_seq=2)
    assert out["id"] == "MSG-1"
    assert captured["url"].endswith("/v2/users/oid1/messages")
    assert captured["body"]["msg_type"] == 7
    assert captured["body"]["media"] == {"file_info": "FI-xxx"}
    assert captured["body"]["msg_id"] == "MID"
    assert captured["body"]["msg_seq"] == 2
    assert "content" not in captured["body"]   # 纯语音无附文


async def test_send_c2c_voice_active_no_msg_id(monkeypatch):
    """无 msg_id → 主动消息(payload 不含 msg_id)"""
    captured = _setup(monkeypatch, lambda r: httpx.Response(200, json={"id": "MSG-2"}))
    await api.send_c2c_voice("oid1", "FI", msg_seq=1)
    assert "msg_id" not in captured["body"]
