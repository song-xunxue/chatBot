"""
记忆 REST 接口测试（httpx.AsyncClient + ASGITransport，与 fakeredis 同 loop）
验证 查看/过滤/手动遗忘/恢复/锁定/批量遗忘/统计/鉴权

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.5 覆盖 rest_memory 全部端点
"""
import pytest
from httpx import AsyncClient, ASGITransport

from core.config import settings
from memory import store
from memory.models import MemoryItem, CoreFact, Category

HEADERS = {"X-Access-Token": settings.access_token}


@pytest.fixture
def app():
    from main import app as _app
    return _app


async def _ac(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_get_memory_empty(app, fake_redis):
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/memory/u", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"core": [], "episodic": [], "long_term": []}


async def test_get_memory_with_data(app, fake_redis):
    await store.upsert_long_term(fake_redis, "u",
        MemoryItem(id="m1", content="猫", category=Category.PREFERENCE))
    await store.set_core(fake_redis, "u", [CoreFact(key="k", content="v")])
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/memory/u", headers=HEADERS)
    d = r.json()
    assert len(d["long_term"]) == 1
    assert len(d["core"]) == 1


async def test_get_memory_filter_category(app, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="a", category=Category.PREFERENCE))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m2", content="b", category=Category.FACT))
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/memory/u?category=preference", headers=HEADERS)
    assert len(r.json()["long_term"]) == 1


async def test_forget_and_restore(app, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="猫"))
    async with await _ac(app) as ac:
        await ac.delete("/api/v1/memory/u/m1", headers=HEADERS)
    assert (await store.get_long_term(fake_redis, "u", "m1")).forgotten is True
    async with await _ac(app) as ac:
        await ac.post("/api/v1/memory/u/restore/m1", headers=HEADERS)
    assert (await store.get_long_term(fake_redis, "u", "m1")).forgotten is False


async def test_batch_forget_by_keyword(app, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="猫A"))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m2", content="猫B"))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m3", content="狗"))
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/memory/u/forget", json={"keyword": "猫"}, headers=HEADERS)
    assert r.json()["forgotten_count"] == 2


async def test_lock(app, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="x"))
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/memory/u/lock/m1", headers=HEADERS)
    assert r.json()["locked"] is True
    assert (await store.get_long_term(fake_redis, "u", "m1")).locked is True


async def test_stats(app, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="a"))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m2", content="b", forgotten=True))
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/memory/u/stats", headers=HEADERS)
    d = r.json()
    assert d["long_term_total"] == 2
    assert d["long_term_active"] == 1
    assert d["long_term_forgotten"] == 1


async def test_auth_required(app, fake_redis):
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/memory/u")
    assert r.status_code == 401


async def test_import_learn(app, fake_redis):
    """F-C-05 导入聊天记录学习：触发事实抽取写入长期记忆"""
    from memory.coordinator import get_memory_coordinator
    from unittest.mock import AsyncMock
    from llm.base import LLMResponse
    coord = await get_memory_coordinator()
    coord.llm = AsyncMock()
    coord.llm.chat.return_value = LLMResponse(
        text='[{"content":"用户喜欢猫","importance":0.8,"emotion":0.5,"category":"preference"}]')
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/memory/u/import",
                          json={"messages": [{"role": "user", "content": "我喜欢猫"}]},
                          headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["imported_facts"] == 1
    items = await store.get_all_long_term(fake_redis, "u")
    assert any("猫" in m.content for m in items)
