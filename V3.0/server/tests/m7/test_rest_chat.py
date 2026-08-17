"""
rest_chat REST 单测(M7):鉴权 / block 列表 / 消息列表 / 取单条(404)/ 编辑 / 软删(联动 neg)/ 关 block。
独立 app(仅挂 chat_router)+ ASGITransport(不走 lifespan)。

作者: 李文煜
日期: 2026-06-30
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_chat import router as chat_router
from core.config import settings
from storage import chat_store
from score import service as score_service

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(chat_router)
    return app


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_chat_auth_required(monkeypatch, fake_redis):
    """无 token → 401"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/chat/u1/blocks")).status_code == 401


async def test_list_blocks_and_messages(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="hi")
    await chat_store.append_message(fake_redis, "u1", sender="ai", content="yo")
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/chat/u1/blocks", headers=_H)
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["msg_count"] == 2
        r2 = await ac.get("/api/v1/chat/u1/messages", headers=_H)
        assert len(r2.json()) == 2


async def test_get_update_delete_with_neg_linkage(monkeypatch, fake_redis):
    """取/编辑/软删(ai+有score → 联动写 neg)"""
    app = _wire(monkeypatch, fake_redis)
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="orig")
    await chat_store.set_score(fake_redis, mid, score_base=40, mood_value=0.5, mood_bias=0)
    async with await _ac(app) as ac:
        # get
        assert (await ac.get(f"/api/v1/chat/messages/{mid}", headers=_H)).json()["content"] == "orig"
        # update → status=edited
        r = await ac.put(f"/api/v1/chat/messages/{mid}", json={"content": "edit"}, headers=_H)
        assert r.json()["status"] == "edited"
        # delete → 联动 neg(httpx delete 不带 body,用 request 传 json)
        r2 = await ac.request("DELETE", f"/api/v1/chat/messages/{mid}",
                              json={"reason": "bad"}, headers=_H)
        assert r2.status_code == 200
        assert r2.json()["neg_linked"] is True
    neg = await score_service.list_samples(fake_redis, "u1", "negative")
    assert len(neg) == 1
    assert neg[0]["mid"] == mid


async def test_delete_user_no_linkage(monkeypatch, fake_redis):
    """user 消息软删不联动 neg"""
    app = _wire(monkeypatch, fake_redis)
    mid = await chat_store.append_message(fake_redis, "u1", sender="user", content="x")
    async with await _ac(app) as ac:
        r = await ac.delete(f"/api/v1/chat/messages/{mid}", headers=_H)
        assert r.json()["neg_linked"] is False
    assert await score_service.list_samples(fake_redis, "u1", "negative") == []


async def test_get_message_404(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/chat/messages/nope", headers=_H)).status_code == 404
        assert (await ac.put("/api/v1/chat/messages/nope", json={}, headers=_H)).status_code == 404
        assert (await ac.delete("/api/v1/chat/messages/nope", headers=_H)).status_code == 404


async def test_close_block(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="x")
    bid = await fake_redis.get(chat_store._active_key("u1"))
    async with await _ac(app) as ac:
        r = await ac.post(f"/api/v1/chat/blocks/{bid}/close", json={"reason": "manual"}, headers=_H)
        assert r.status_code == 200
    block = await chat_store.list_blocks(fake_redis, "u1")
    assert block[0]["status"] == "closed"
    assert block[0]["close_reason"] == "manual"


async def test_list_sessions(monkeypatch, fake_redis):
    """GET /chat/sessions 列最近活跃会话(无 token→401;有 token→两会话 + last_ts/block_count)"""
    app = _wire(monkeypatch, fake_redis)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="a")
    await chat_store.append_message(fake_redis, "u2", sender="user", content="b")
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/chat/sessions")).status_code == 401
        r = await ac.get("/api/v1/chat/sessions", headers=_H)
        assert r.status_code == 200
        data = r.json()
        assert {s["object_id"] for s in data} == {"u1", "u2"}
        for s in data:
            assert "last_ts" in s and "block_count" in s
