"""
webhook 代答联动单测:代答开 → C2C 消息入 pending 队列不进 pipeline;代答关 → 走防抖。
用 ASGITransport + 合法签名 payload + fakeredis 注入 + mock _schedule_debounce。

作者: 李文煜
日期: 2026-06-30
"""
import json

import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from qq.webhook import router as qq_router
from storage import takeover_store


def _c2c_body(openid: str, content: str, msg_id: str = "MID") -> bytes:
    """构造 C2C_MESSAGE_CREATE 事件 body"""
    return json.dumps({
        "op": 0, "t": "C2C_MESSAGE_CREATE",
        "d": {"author": {"user_openid": openid}, "content": content, "id": msg_id},
    }).encode()


async def test_takeover_on_enqueues_not_pipeline(monkeypatch, fake_redis, make_signature, now_ts):
    """代答开 → C2C 消息入 pending 队列,_schedule_debounce 未调用(不进 pipeline)"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    await takeover_store.set_enabled(fake_redis, "OID1", True)
    debounced = {"n": 0}

    async def _noop_debounce(msg):
        debounced["n"] += 1
    monkeypatch.setattr("qq.webhook._schedule_debounce", _noop_debounce)

    body = _c2c_body("OID1", "在吗")
    sig = make_signature(now_ts, body)
    app = FastAPI()
    app.include_router(qq_router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post("/qq/webhook", content=body,
                          headers={"X-Signature-Ed25519": sig, "X-Signature-Timestamp": now_ts})
    assert r.status_code == 200
    assert debounced["n"] == 0                          # 没进防抖
    q = await takeover_store.list_queue(fake_redis, "OID1")
    assert len(q) == 1
    assert q[0]["user_text"] == "在吗"
    assert q[0]["msg_id"] == "MID"


async def test_takeover_off_goes_debounce(monkeypatch, fake_redis, make_signature, now_ts):
    """代答关 → C2C 消息走防抖(_schedule_debounce 被调),不入队"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    # 代答关(默认即关)
    debounced = {"n": 0}

    async def _noop_debounce(msg):
        debounced["n"] += 1
    monkeypatch.setattr("qq.webhook._schedule_debounce", _noop_debounce)

    body = _c2c_body("OID2", "正常消息")
    sig = make_signature(now_ts, body)
    app = FastAPI()
    app.include_router(qq_router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post("/qq/webhook", content=body,
                          headers={"X-Signature-Ed25519": sig, "X-Signature-Timestamp": now_ts})
    assert r.status_code == 200
    assert debounced["n"] == 1                          # 走防抖
    assert await takeover_store.list_queue(fake_redis, "OID2") == []   # 没入队
