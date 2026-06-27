"""
coordinator M4 增强单测:retrieve 用 BM25 rank + 加权随机召回 / forget_tick 整合睡眠巩固。
直接构造 MemoryCoordinator(不经单例,避免跨测试缓存)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M4 创建 coordinator 增强单测(BM25 召回 / 加权随机多样性 / forget_tick 整合 consolidate)
"""
from core.config import settings
from memory import store
from memory.models import MemoryItem, EpisodicEntry
from memory.coordinator import MemoryCoordinator


async def test_retrieve_bm25_recall(fake_redis, monkeypatch):
    """retrieve:放入 long-term,BM25 rank 召回命中 query 的条目"""
    monkeypatch.setattr(settings, "memory_weighted_sample", False)   # 确定性便于断言
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    await store.upsert_long_term(fake_redis, "u1", MemoryItem(id="m1", content="用户喜欢猫"))
    await store.upsert_long_term(fake_redis, "u1", MemoryItem(id="m2", content="今天天气不错"))
    res = await coord.retrieve("u1", "猫", top_k=5)
    assert "m1" in {m.id for m in res.long_term}     # 命中"猫"
    assert "m2" not in {m.id for m in res.long_term}  # 不命中


async def test_retrieve_weighted_sample_diversifies(fake_redis):
    """加权随机召回:候选多于 top_k 时,多次召回覆盖 > top_k 的不同条目(避确定性偏见)"""
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    for i in range(8):
        await store.upsert_long_term(fake_redis, "u1", MemoryItem(id=f"m{i}", content=f"猫{i}"))
    seen: set[str] = set()
    for _ in range(20):
        res = await coord.retrieve("u1", "猫", top_k=3)
        seen |= {m.id for m in res.long_term}
    assert len(seen) > 3    # 加权随机应覆盖多于 top_k 的不同条目


async def test_retrieve_touch_updates_access(fake_redis, monkeypatch):
    """召回即访问:被召回条目 access_count + 1"""
    monkeypatch.setattr(settings, "memory_weighted_sample", False)
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    await store.upsert_long_term(fake_redis, "u1", MemoryItem(id="m1", content="用户喜欢猫"))
    await coord.retrieve("u1", "猫", top_k=5)
    m = await store.get_long_term(fake_redis, "u1", "m1")
    assert m.access_count == 1


async def test_forget_tick_integrates_consolidate(fake_redis, monkeypatch):
    """forget_tick 末尾整合睡眠巩固:episodic 超 keep 被清理"""
    monkeypatch.setattr(settings, "memory_episodic_keep", 2)
    monkeypatch.setattr(settings, "memory_consolidate_enable", True)
    # u1 需有 long-term 才会被 list_objects 扫到(forget_tick 遍历 long key)
    await store.upsert_long_term(fake_redis, "u1", MemoryItem(id="lm1", content="已有事实"))
    for i in range(5):
        await store.append_episodic(fake_redis, "u1", EpisodicEntry(
            id=f"e{i}", summary=f"s{i}", span_start_ts=i, span_end_ts=i, created_ts=i * 1000))
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    await coord.forget_tick()
    assert await store.count_episodic(fake_redis, "u1") == 2   # 5 → 留最近 2
