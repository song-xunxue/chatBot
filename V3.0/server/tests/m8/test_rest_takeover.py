"""
对话控制 REST 单测(2026-09-13 队列删减重构版)
覆盖:鉴权 / toggle+status(AI 静默开关)/ send(主动发送+空 400)/ tts_config / oid QQ 号校验。
原队列端点族(queue/answer/batch/skip/clear)测试已移除。

作者: 李文煜
日期: 2026-06-30

2026-09-13
变更说明：
  1. 队列删减:删队列端点测试;status 不再有 queue_length
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_takeover import router as takeover_router
from core.config import settings

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    """注入 fakeredis + access_token,返回仅挂 takeover_router 的 app"""
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(takeover_router)
    return app


async def _aclient(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_auth_required(monkeypatch, fake_redis):
    """无 token / 错 token → 401"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        assert (await ac.get("/api/v1/takeover/10001/status")).status_code == 401
        assert (await ac.get("/api/v1/takeover/10001/status",
                             headers={"X-Access-Token": "wrong"})).status_code == 401


async def test_toggle_and_status(monkeypatch, fake_redis):
    """AI 静默开关 toggle + status 反映(无 queue_length)"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/takeover/10001/toggle", json={"enabled": True}, headers=_H)
        assert r.json()["enabled"] is True
        r = await ac.get("/api/v1/takeover/10001/status", headers=_H)
        assert r.json() == {"object_id": "10001", "enabled": True}
        assert "queue_length" not in r.json()          # 队列已删


async def test_send_endpoint(monkeypatch, fake_redis, fake_adapter):
    """主动发送:落 proxy + 下发;空 content → 400"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/takeover/10001/send", json={"content": "主动"}, headers=_H)
        data = r.json()
        assert data["delivered"] is True and "proxy_mid" in data
        r2 = await ac.post("/api/v1/takeover/10001/send", json={"content": "  "}, headers=_H)
        assert r2.status_code == 400


async def test_non_qq_oid_rejected_400(monkeypatch, fake_redis, fake_adapter):
    """oid 必须 QQ 号(纯数字),default 等全端点 400(2026-08-18 沿用)"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        for path, payload in [
            ("/api/v1/takeover/default/send", {"content": "x"}),
            ("/api/v1/takeover/default/toggle", {"enabled": True}),
        ]:
            r = await ac.post(path, json=payload, headers=_H)
            assert r.status_code == 400, path
            assert "QQ" in r.json()["detail"]
        assert (await ac.get("/api/v1/takeover/default/status", headers=_H)).status_code == 400


async def test_tts_config_roundtrip(monkeypatch, fake_redis):
    """tts_config GET/PUT 往返"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.get("/api/v1/takeover/10001/tts_config", headers=_H)
        assert r.json()["enable"] is False
        r = await ac.put("/api/v1/takeover/10001/tts_config",
                         json={"enable": True, "send_text_also": True}, headers=_H)
        assert r.json() == {"object_id": "10001", "enable": True, "send_text_also": True}
        r2 = await ac.get("/api/v1/takeover/10001/tts_config", headers=_H)
        assert r2.json()["enable"] is True
