"""
代答 REST 接口单测(httpx.AsyncClient + ASGITransport):鉴权/toggle/status/queue/answer/answer-batch/skip。
独立 app(仅挂 takeover_router,无 lifespan)+ fakeredis 注入 + mock send_c2c_message。

作者: 李文煜
日期: 2026-06-30
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_takeover import router as takeover_router
from core.config import settings
from storage import takeover_store

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    """注入 fakeredis + access_token + 关 memory(mock send 下发由各用例 monkeypatch)"""
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    monkeypatch.setattr(settings, "memory_enabled", False)
    app = FastAPI()
    app.include_router(takeover_router)
    return app


async def _aclient(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _noop_send(oid, content, *, msg_id="", msg_seq=1, human_authored=False):
    return {"id": "MSG"}


async def test_auth_required(monkeypatch, fake_redis):
    """无 token / 错 token → 401"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        assert (await ac.get("/api/v1/takeover/u1/status")).status_code == 401
        assert (await ac.get("/api/v1/takeover/u1/status", headers={"X-Access-Token": "wrong"})).status_code == 401


async def test_toggle_and_status(monkeypatch, fake_redis):
    """toggle 开/关 + status 反映"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/takeover/u1/toggle", json={"enabled": True}, headers=_H)
        assert r.json()["enabled"] is True
        r = await ac.get("/api/v1/takeover/u1/status", headers=_H)
        assert r.json()["enabled"] is True
        assert r.json()["queue_length"] == 0


async def test_queue_listing(monkeypatch, fake_redis):
    """enqueue 后 queue 列出"""
    app = _wire(monkeypatch, fake_redis)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi", msg_id="MID")
    async with await _aclient(app) as ac:
        r = await ac.get("/api/v1/takeover/u1/queue", headers=_H)
        q = r.json()["queue"]
        assert len(q) == 1
        assert q[0]["user_text"] == "hi"


async def test_answer_404_when_empty(monkeypatch, fake_redis):
    """空队列 answer → 404"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/takeover/u1/answer", json={"answer": "答"}, headers=_H)
        assert r.status_code == 404


async def test_answer_success(monkeypatch, fake_redis):
    """enqueue + answer → 200 delivered"""
    app = _wire(monkeypatch, fake_redis)
    monkeypatch.setattr("qq.api_client.send_c2c_message", _noop_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi", msg_id="MID")
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/takeover/u1/answer", json={"answer": "代答"}, headers=_H)
        data = r.json()
        assert data["delivered"] is True
        assert data["mode"] == "passive"
        assert "proxy_mid" in data


async def test_answer_batch(monkeypatch, fake_redis):
    """批量代答:两条 pending 一次清空"""
    app = _wire(monkeypatch, fake_redis)
    monkeypatch.setattr("qq.api_client.send_c2c_message", _noop_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    await takeover_store.enqueue(fake_redis, "u1", user_text="m2")
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/takeover/u1/answer/batch",
                          json={"items": [{"answer": "a1"}, {"answer": "a2"}]}, headers=_H)
        data = r.json()
        assert data["success"] == 2
        assert len(data["results"]) == 2


async def test_skip(monkeypatch, fake_redis):
    """跳过队首"""
    app = _wire(monkeypatch, fake_redis)
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="跳我")
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/takeover/u1/skip", json={}, headers=_H)
        assert r.json()["skipped"] is True
    assert await takeover_store.list_queue(fake_redis, "u1") == []
