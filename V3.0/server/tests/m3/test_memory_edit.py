"""
记忆编辑单测(2026-07-06):store.update_long_term + rest PATCH /memory/{oid}/{mid}。
手动修正错误记忆(如人称混淆)。store 层直传 fake_redis;rest 层 httpx ASGITransport。

作者: 李文煜
日期: 2026-07-06
"""
import pytest
import httpx
import fakeredis
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_memory import router as memory_router
from core.config import settings
from memory import store
from memory.models import MemoryItem, Category

_H = {"X-Access-Token": "t-token"}


@pytest.fixture
def fake_redis():
    yield fakeredis.FakeAsyncRedis(decode_responses=True)


async def _aclient(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_update_long_term(fake_redis):
    """编辑长期记忆:content/category/importance;其他字段(locked/access_count)保留"""
    m = MemoryItem(id="m1", content="原内容", category=Category.FACT, importance=0.5, locked=True)
    await store.upsert_long_term(fake_redis, "u1", m)
    ok = await store.update_long_term(
        fake_redis, "u1", "m1", content="改后", category=Category.PREFERENCE, importance=0.9)
    assert ok is True
    updated = await store.get_long_term(fake_redis, "u1", "m1")
    assert updated.content == "改后"
    assert updated.category == Category.PREFERENCE
    assert updated.importance == 0.9
    assert updated.locked is True            # 其他字段保留
    # importance 钳到 [0,1]
    await store.update_long_term(fake_redis, "u1", "m1", importance=5.0)
    assert (await store.get_long_term(fake_redis, "u1", "m1")).importance == 1.0
    # 不存在 → False
    assert await store.update_long_term(fake_redis, "u1", "nope", content="x") is False


async def test_edit_memory_endpoint(monkeypatch, fake_redis):
    """PATCH /memory/{oid}/{mid} 编辑 + 校验(400/404)"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    monkeypatch.setattr(settings, "access_token", "t-token")
    await store.upsert_long_term(
        fake_redis, "u1", MemoryItem(id="m1", content="原", category=Category.FACT, importance=0.5))
    app = FastAPI()
    app.include_router(memory_router)
    async with await _aclient(app) as ac:
        # 改 content + category + importance
        r = await ac.patch("/api/v1/memory/u1/m1",
                           json={"content": "改后", "category": "relationship", "importance": 0.8}, headers=_H)
        data = r.json()
        assert data["content"] == "改后"
        assert data["category"] == "relationship"
        assert data["importance"] == 0.8
        # 无字段 → 400
        assert (await ac.patch("/api/v1/memory/u1/m1", json={}, headers=_H)).status_code == 400
        # 非法 category → 400
        assert (await ac.patch("/api/v1/memory/u1/m1", json={"category": "bad"}, headers=_H)).status_code == 400
        # 不存在 → 404
        assert (await ac.patch("/api/v1/memory/u1/nope", json={"content": "x"}, headers=_H)).status_code == 404
