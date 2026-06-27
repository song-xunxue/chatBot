"""
consolidation 单测(M4):consolidate_sleep 睡眠巩固
(LLM 提炼 episodic→long-term fact + importance 阈值 + 冗余 episodic 清理 / 无 LLM 降级只清理)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M4 创建 consolidation 单测(提炼固化 / importance 阈值过滤 / 无 LLM 降级清理 / episodic 裁剪)
"""
from core.config import settings
from memory import store
from memory.models import EpisodicEntry
from memory.coordinator import MemoryCoordinator
from memory.consolidation import consolidate_sleep


async def test_consolidate_extracts_facts_to_long_term(fake_redis, make_provider, monkeypatch):
    """有 LLM:episodic 摘要 → 提炼 fact(importance 达阈)→ 去重入 long-term"""
    monkeypatch.setattr(settings, "memory_consolidate_importance", 0.5)
    await store.append_episodic(fake_redis, "u1", EpisodicEntry(
        id="e1", summary="用户提到喜欢猫", span_start_ts=1, span_end_ts=2, created_ts=10))
    provider = make_provider('[{"content":"用户喜欢猫","importance":0.8,"emotion":0.5,"category":"preference"}]')
    coord = MemoryCoordinator(fake_redis, llm_provider=provider)

    res = await consolidate_sleep(fake_redis, "u1", coord.llm, "", coordinator=coord)
    assert res["facts_added"] == 1
    items = await store.get_all_long_term(fake_redis, "u1")
    assert any("猫" in m.content for m in items)


async def test_consolidate_low_importance_filtered(fake_redis, make_provider, monkeypatch):
    """importance 低于阈值的 fact 不固化"""
    monkeypatch.setattr(settings, "memory_consolidate_importance", 0.7)
    await store.append_episodic(fake_redis, "u1", EpisodicEntry(
        id="e1", summary="闲聊", span_start_ts=1, span_end_ts=2, created_ts=10))
    provider = make_provider('[{"content":"无关琐事","importance":0.3,"emotion":0.0,"category":"fact"}]')
    coord = MemoryCoordinator(fake_redis, llm_provider=provider)
    res = await consolidate_sleep(fake_redis, "u1", coord.llm, "", coordinator=coord)
    assert res["facts_added"] == 0
    assert await store.get_all_long_term(fake_redis, "u1") == []


async def test_consolidate_no_llm_only_prunes(fake_redis, monkeypatch):
    """无 LLM:跳过提炼,仍做 episodic 冗余清理(降级)"""
    monkeypatch.setattr(settings, "memory_episodic_keep", 2)
    for i in range(5):
        await store.append_episodic(fake_redis, "u1", EpisodicEntry(
            id=f"e{i}", summary=f"s{i}", span_start_ts=i, span_end_ts=i, created_ts=i))
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    res = await consolidate_sleep(fake_redis, "u1", None, "", coordinator=coord)
    assert res["facts_added"] == 0
    assert res["episodic_pruned"] == 3          # 5 → 留最近 2
    assert await store.count_episodic(fake_redis, "u1") == 2


async def test_consolidate_prunes_keeps_recent(fake_redis, make_provider, monkeypatch):
    """清理后保留的是最近(created_ts 最大)的 episodic"""
    monkeypatch.setattr(settings, "memory_episodic_keep", 2)
    for i in range(4):
        await store.append_episodic(fake_redis, "u1", EpisodicEntry(
            id=f"e{i}", summary=f"s{i}", span_start_ts=i, span_end_ts=i, created_ts=(i + 1) * 1000))
    coord = MemoryCoordinator(fake_redis, llm_provider=None)
    await consolidate_sleep(fake_redis, "u1", None, "", coordinator=coord)
    eps = await store.get_episodic(fake_redis, "u1", limit=10)
    sums = {e.summary for e in eps}
    assert sums == {"s2", "s3"}                 # 留最近两条(created_ts 3000/4000)
