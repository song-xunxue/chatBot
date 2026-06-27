"""
rest_memory REST 单测(httpx.AsyncClient + ASGITransport,全 async):
鉴权 / 查看(layer+category 过滤)/ 统计 / 手动遗忘+恢复 / 锁定 / 批量遗忘。
独立 app(仅挂 memory_router);每测 reset_coordinator 避免 coordinator 单例跨测试缓存旧 redis。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M4 创建 rest_memory 单测(鉴权/查看+过滤/统计/遗忘+恢复/锁定/批量遗忘)
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_memory import router as memory_router
from core.config import settings
from memory import store
from memory.models import MemoryItem, EpisodicEntry, CoreFact
from memory.coordinator import reset_coordinator

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    """注入 fakeredis + access_token + 重置 coordinator 单例,返回独立 app"""
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    reset_coordinator()                     # 避免单例缓存上一个测试的 fake
    app = FastAPI()
    app.include_router(memory_router)
    return app


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_auth_required(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/memory/u1")).status_code == 401


async def test_view_all_layers_and_category_filter(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await store.upsert_long_term(fake_redis, "u1",
                                 MemoryItem(id="m1", content="喜欢猫", category="preference"))
    await store.append_episodic(fake_redis, "u1", EpisodicEntry(
        id="e1", summary="聊了猫", span_start_ts=1, span_end_ts=2, created_ts=10))
    await store.set_core(fake_redis, "u1", [CoreFact(key="name", content="小明")])

    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/memory/u1", headers=_H)
        assert r.status_code == 200
        body = r.json()
        assert len(body["core"]) == 1
        assert len(body["episodic"]) == 1
        assert len(body["long_term"]) == 1
        # category 过滤命中
        r2 = await ac.get("/api/v1/memory/u1?layer=long_term&category=preference", headers=_H)
        assert len(r2.json()["long_term"]) == 1
        # category 不命中
        r3 = await ac.get("/api/v1/memory/u1?layer=long_term&category=fact", headers=_H)
        assert len(r3.json()["long_term"]) == 0


async def test_stats(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await store.upsert_long_term(fake_redis, "u1", MemoryItem(id="m1", content="a"))
    await store.append_episodic(fake_redis, "u1", EpisodicEntry(
        id="e1", summary="s", span_start_ts=1, span_end_ts=2, created_ts=10))
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/memory/u1/stats", headers=_H)
        assert r.status_code == 200
        body = r.json()
        assert body["episodic"] == 1
        assert body["long_term_active"] == 1
        assert body["long_term_forgotten"] == 0


async def test_manual_forget_restore_lock(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await store.upsert_long_term(fake_redis, "u1", MemoryItem(id="m1", content="x"))
    async with await _ac(app) as ac:
        assert (await ac.delete("/api/v1/memory/u1/m1", headers=_H)).json()["forgotten"] is True
        assert (await ac.post("/api/v1/memory/u1/m1/restore", headers=_H)).json()["restored"] is True
        assert (await ac.post("/api/v1/memory/u1/m1/lock",
                              json={"locked": True}, headers=_H)).json()["locked"] is True
        # 不存在 404
        assert (await ac.delete("/api/v1/memory/u1/nope", headers=_H)).status_code == 404


async def test_batch_forget_by_category(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await store.upsert_long_term(fake_redis, "u1", MemoryItem(id="m1", content="猫", category="preference"))
    await store.upsert_long_term(fake_redis, "u1", MemoryItem(id="m2", content="狗", category="fact"))
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/memory/u1/forget",
                          json={"category": "preference"}, headers=_H)
        assert r.status_code == 200
        assert r.json()["forgotten"] == 1
