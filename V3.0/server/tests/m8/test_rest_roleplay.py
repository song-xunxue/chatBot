"""
roleplay REST 接口单测(httpx.AsyncClient + ASGITransport):鉴权/录/批量/列/改/删(→neg)。
独立 app(仅挂 roleplay_router)+ fakeredis 注入。

作者: 李文煜
日期: 2026-06-30
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_roleplay import router as roleplay_router
from core.config import settings

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(roleplay_router)
    return app


async def _aclient(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_auth_required(monkeypatch, fake_redis):
    """无 token → 401"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        assert (await ac.get("/api/v1/roleplay/u1/messages")).status_code == 401


async def test_add_list_update_delete(monkeypatch, fake_redis):
    """录 → 列 → 改 → 删 全流程"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        # 录
        r = await ac.post("/api/v1/roleplay/u1/messages",
                          json={"role": "user", "content": "你好"}, headers=_H)
        mid = r.json()["mid"]
        assert mid.startswith("rp_")
        # 列
        r = await ac.get("/api/v1/roleplay/u1/messages", headers=_H)
        assert len(r.json()["messages"]) == 1
        # 改
        r = await ac.put(f"/api/v1/roleplay/u1/messages/{mid}",
                         json={"content": "改后"}, headers=_H)
        assert r.json()["updated"] is True
        # 删
        r = await ac.delete(f"/api/v1/roleplay/u1/messages/{mid}", headers=_H)
        assert r.json()["deleted"] is True
        # 列空
        r = await ac.get("/api/v1/roleplay/u1/messages", headers=_H)
        assert r.json()["messages"] == []


async def test_batch(monkeypatch, fake_redis):
    """批量录连发"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/roleplay/u1/messages/batch", json={
            "items": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        }, headers=_H)
        assert r.json()["count"] == 2


async def test_invalid_role_400(monkeypatch, fake_redis):
    """非法 role → 400"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/roleplay/u1/messages",
                          json={"role": "robot", "content": "x"}, headers=_H)
        assert r.status_code == 400


async def test_sessions_and_score(monkeypatch, fake_redis):
    """新建会话 + 列会话 + 录 assistant(带分) + 改分(2026-07-05)"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        # 新建会话
        r = await ac.post("/api/v1/roleplay/u1/sessions", headers=_H)
        bid = r.json()["block_id"]
        assert bid
        # 列会话
        r = await ac.get("/api/v1/roleplay/u1/sessions", headers=_H)
        assert len(r.json()) == 1
        # 录 assistant + score
        r = await ac.post("/api/v1/roleplay/u1/messages",
                          json={"role": "assistant", "content": "hi", "score_base": 90}, headers=_H)
        mid = r.json()["mid"]
        # 改分
        r = await ac.patch(f"/api/v1/roleplay/u1/messages/{mid}/score",
                           json={"score_base": 50}, headers=_H)
        assert r.json()["score"] == 50
        # 列消息含 score
        r = await ac.get("/api/v1/roleplay/u1/messages", headers=_H)
        assert r.json()["messages"][0]["score"] == "50"
        # 改分缺 score_base → 400
        r = await ac.patch(f"/api/v1/roleplay/u1/messages/{mid}/score", json={}, headers=_H)
        assert r.status_code == 400
        # block_id 过滤
        r = await ac.get(f"/api/v1/roleplay/u1/messages?block_id={bid}", headers=_H)
        assert len(r.json()["messages"]) == 1
