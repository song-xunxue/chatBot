"""
记忆三要素 + useful_score 三档衰减闭环单测(2026-08-13):
1. _parse_facts 解析 reason/tags
2. _upsert_fact_dedup 新建带 reason/tags/useful_score;去重合并 reason 取非空/tags 并集/useful_score 取 max
3. MemoryItem.from_dict 老数据(无新字段)→ 默认值(免迁移兼容)
4. should_forget 三档:手动 T2 永不 / T1 看 useful_score / T0 看 retain_score;自动档由 useful_score;locked 豁免
5. on_turn_complete RL:本轮 score>=85 召回记忆 useful_score += δ;<60 -= δ;手动档/锁定不动

作者: 李文煜
日期: 2026-08-13
"""
import json

from memory.encoder import _parse_facts
from memory.models import MemoryItem, Category, ForgetConfig
from memory.forgetting import should_forget, _auto_tier
from memory.coordinator import MemoryCoordinator


# —— 1. _parse_facts 解析 reason/tags ——
def test_parse_facts_with_reason_tags():
    """三要素:_parse_facts 解析 reason + tags(缺省/非list 容错)"""
    text = json.dumps([
        {"content": "用户喜欢动漫", "importance": 0.8, "category": "preference",
         "reason": "用户多次主动提起", "tags": ["喜好", "日常"]},
        {"content": "用户会编程", "importance": 0.5, "category": "fact"},   # 无 reason/tags
        {"content": "异常标签", "importance": 0.5, "tags": "不是数组"},     # tags 非 list
    ])
    facts = _parse_facts(text)
    assert len(facts) == 3
    assert facts[0]["reason"] == "用户多次主动提起"
    assert facts[0]["tags"] == ["喜好", "日常"]
    assert facts[1]["reason"] == ""
    assert facts[1]["tags"] == []
    assert facts[2]["tags"] == []   # 非 list 容错为空


# —— 2. _upsert_fact_dedup 新建 + 去重合并 ——
async def test_upsert_new_with_three_fields(fake_redis):
    """新建记忆带 reason/tags/useful_score(useful_score 默认=importance)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    fact = {"content": "用户喜欢动漫", "importance": 0.8, "emotion": 0.0,
            "category": "preference", "reason": "多次提及", "tags": ["喜好"]}
    written = await c._upsert_fact_dedup("u1", fact)
    assert written is True
    from memory import store
    items = await store.get_all_long_term(fake_redis, "u1")
    assert len(items) == 1
    assert items[0].reason == "多次提及"
    assert items[0].tags == ["喜好"]
    assert abs(items[0].useful_score - 0.8) < 1e-6   # 默认 init=importance


async def test_upsert_dedup_merge_three_fields(fake_redis):
    """去重合并:reason 取非空者 / tags 并集 / useful_score 取 max(巩固)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.6,
                                      "category": "preference", "reason": "", "tags": ["喜好"]})
    # 第二次命中去重(同内容),新 reason 非空 + 新 tag + 高 useful_score
    written = await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.7,
                                                "category": "preference",
                                                "reason": "用户多次主动提起",
                                                "tags": ["日常", "喜好"]})
    assert written is False   # 命中去重
    from memory import store
    items = await store.get_all_long_term(fake_redis, "u1")
    assert len(items) == 1
    m = items[0]
    assert m.reason == "用户多次主动提起"          # 旧空→取新非空
    assert set(m.tags) == {"喜好", "日常"}          # 并集
    assert abs(m.importance - 0.7) < 1e-6          # max
    assert m.access_count == 1                      # 命中 +1


# —— 3. 兼容性:老数据免迁移 ——
def test_from_dict_legacy_compat():
    """老 JSON(无 reason/tags/useful_score/tier)→ from_dict 补默认,免迁移"""
    raw = {
        "id": "mem_x", "content": "老记忆", "category": "fact",
        "importance": 0.5, "emotion": 0.0,
        "created_ts": 1, "last_access_ts": 1, "access_count": 0,
        "forgotten": False, "source": "dialog", "locked": False,
    }
    m = MemoryItem.from_dict(raw)
    assert m.reason == ""
    assert m.tags == []
    assert abs(m.useful_score - 0.5) < 1e-6
    assert m.tier == -1


# —— 4. 三档衰减判定 ——
def _cfg():
    return ForgetConfig(tier0_threshold=0.3, tier1_threshold=0.7, retain_threshold=0.3)


def test_auto_tier_by_useful_score():
    """自动档:useful_score→T2/T1/T0(由 _auto_tier 推)"""
    cfg = _cfg()
    assert _auto_tier(MemoryItem(id="a", content="x", useful_score=0.9), cfg) == 2
    assert _auto_tier(MemoryItem(id="b", content="x", useful_score=0.5), cfg) == 1
    assert _auto_tier(MemoryItem(id="c", content="x", useful_score=0.1), cfg) == 0


def test_should_forget_manual_tier2_never():
    """手动 T2 永不遗忘(useful_score 很低也不忘)"""
    cfg = _cfg()
    m = MemoryItem(id="x", content="x", useful_score=0.01, tier=2)
    assert should_forget(m, cfg) is False


def test_should_forget_manual_tier1_by_useful_score():
    """手动 T1:只在 useful_score 跌破 tier0_threshold 才忘"""
    cfg = _cfg()
    m_ok = MemoryItem(id="x", content="x", useful_score=0.5, tier=1)
    assert should_forget(m_ok, cfg) is False           # 高分不忘
    m_low = MemoryItem(id="x", content="x", useful_score=0.1, tier=1)
    assert should_forget(m_low, cfg) is True           # 跌破→忘


def test_should_forget_locked_exempt():
    """locked 强制永不(即便 T0 衰减也不忘)"""
    cfg = _cfg()
    m = MemoryItem(id="x", content="x", useful_score=0.0, tier=0, locked=True)
    assert should_forget(m, cfg) is False


def test_should_forget_auto_tier0_natural_decay():
    """自动 T0(useful_score 低):retain_score 跌破阈值→忘(老逻辑保留)"""
    cfg = _cfg()
    # access_count=0/importance 低/很久没访问 → retain_score 极低
    m = MemoryItem(id="x", content="x", useful_score=0.05, importance=0.0,
                   created_ts=1, last_access_ts=1)   # ts=1 = 很久以前
    assert should_forget(m, cfg) is True


# —— 5. on_turn_complete RL useful_score 增减 ——
async def test_rl_useful_score_high_score_reinforce(fake_redis, monkeypatch):
    """本轮 score>=85 → 被召回记忆 useful_score += δ(强化)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    # 预置一条记忆 + 标记为本轮召回
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.5,
                                      "category": "preference"})   # useful_score=0.5
    from memory import store
    items = await store.get_all_long_term(fake_redis, "u1")
    mid = items[0].id

    class FakeCtx:
        object_id = "u1"
        last_score = 90.0                    # >=85 强化
        memory_meta = {"hit_mids": [mid]}    # 本轮召回了这条

    from core.config import settings
    monkeypatch.setattr(settings, "memory_useful_score_delta", 0.1)
    async with c._lock("u1"):
        await c._apply_score_to_recalled("u1", FakeCtx(), sign=1)

    m = await store.get_long_term(fake_redis, "u1", mid)
    assert abs(m.useful_score - 0.6) < 1e-6   # 0.5 + 0.1


async def test_rl_useful_score_manual_tier_skipped(fake_redis, monkeypatch):
    """手动档 tier>=0 的记忆:RL 增减跳过(不动用户显式设定)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    from memory import store
    from memory.models import MemoryItem, Category
    item = MemoryItem(id="mem_manual", content="手动", category=Category.FACT,
                      importance=0.5, useful_score=0.5, tier=2)   # 手动 T2
    await store.upsert_long_term(fake_redis, "u1", item)

    class FakeCtx:
        object_id = "u1"
        last_score = 90.0
        memory_meta = {"hit_mids": ["mem_manual"]}

    from core.config import settings
    monkeypatch.setattr(settings, "memory_useful_score_delta", 0.1)
    async with c._lock("u1"):
        await c._apply_score_to_recalled("u1", FakeCtx(), sign=1)

    m = await store.get_long_term(fake_redis, "u1", "mem_manual")
    assert abs(m.useful_score - 0.5) < 1e-6   # 未动
