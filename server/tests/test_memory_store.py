"""
四级记忆存储原语测试（fakeredis）
验证 Core/Episodic/Reflect/Long-term/State 各层读写、键隔离、访问统计、遗忘标记、
Working 委托 chat_store、对象索引扫描、chat_store 前缀与向后兼容

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.2 覆盖 memory.store 各层接口
"""
import json

from memory import store
from memory.models import MemoryItem, EpisodicEntry, CoreFact, Category


# ===== Long-term =====
async def test_long_term_upsert_get(fake_redis):
    item = MemoryItem(id="m1", content="用户喜欢猫", category=Category.PREFERENCE, importance=0.8)
    await store.upsert_long_term(fake_redis, "u1", item)
    got = await store.get_long_term(fake_redis, "u1", "m1")
    assert got is not None
    assert got.content == "用户喜欢猫"
    assert got.category == Category.PREFERENCE
    assert got.importance == 0.8


async def test_long_term_hash_schema_full_fields(fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m", content="x", emotion=0.6))
    raw = await fake_redis.hget(store._K_LONG.format(oid="u"), "m")
    d = json.loads(raw)
    for k in ["id", "content", "category", "importance", "emotion",
              "created_ts", "last_access_ts", "access_count", "forgotten", "source"]:
        assert k in d


async def test_long_term_get_all_excludes_forgotten(fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="a", content="A"))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="b", content="B", forgotten=True))
    active = await store.get_all_long_term(fake_redis, "u")
    assert {m.id for m in active} == {"a"}
    allm = await store.get_all_long_term(fake_redis, "u", include_forgotten=True)
    assert {m.id for m in allm} == {"a", "b"}


async def test_touch_updates_access_stats(fake_redis):
    await store.upsert_long_term(fake_redis, "u",
                                 MemoryItem(id="a", content="A", last_access_ts=1000, access_count=0))
    await store.touch_long_term(fake_redis, "u", ["a"])
    m = await store.get_long_term(fake_redis, "u", "a")
    assert m.access_count == 1
    assert m.last_access_ts > 1000  # 间隔重复：重置衰减


async def test_mark_and_restore_forgotten(fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="a", content="A"))
    await store.mark_forgotten(fake_redis, "u", ["a"])
    assert (await store.get_long_term(fake_redis, "u", "a")).forgotten is True
    await store.restore_long_term(fake_redis, "u", ["a"])
    assert (await store.get_long_term(fake_redis, "u", "a")).forgotten is False


async def test_delete_long_term(fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="a", content="A"))
    await store.delete_long_term(fake_redis, "u", ["a"])
    assert await store.get_long_term(fake_redis, "u", "a") is None


# ===== Core =====
async def test_core_set_get(fake_redis):
    facts = [CoreFact(key="user_name", content="小明"),
             CoreFact(key="trait", content="温柔", locked=True)]
    await store.set_core(fake_redis, "u", facts)
    got = await store.get_core(fake_redis, "u")
    assert len(got) == 2
    assert got[0].content == "小明"
    assert got[1].locked is True


async def test_core_empty_when_absent(fake_redis):
    assert await store.get_core(fake_redis, "nobody") == []


# ===== Episodic =====
async def test_episodic_append_and_recent_desc(fake_redis):
    for i in range(5):
        await store.append_episodic(fake_redis, "u", EpisodicEntry(
            id=f"e{i}", summary=f"摘要{i}", span_start_ts=i, span_end_ts=i, created_ts=1000 + i))
    recent = await store.get_episodic(fake_redis, "u", limit=3)
    assert len(recent) == 3
    assert recent[0].created_ts == 1004  # 倒序：最近的最大
    assert await store.count_episodic(fake_redis, "u") == 5


# ===== Reflect =====
async def test_reflection_append_get(fake_redis):
    await store.append_reflection(fake_redis, "u", "用户最近常聊工作", span=(0, 10))
    rs = await store.get_reflections(fake_redis, "u")
    assert len(rs) == 1
    assert rs[0]["reflection"] == "用户最近常聊工作"


# ===== State =====
async def test_state_set_get(fake_redis):
    await store.set_state(fake_redis, "u", {"mood": "开心", "energy": 0.6})
    st = await store.get_state(fake_redis, "u")
    assert st["mood"] == "开心"
    assert "updated_ts" in st


# ===== 键隔离 =====
async def test_key_isolation_between_objects(fake_redis):
    await store.upsert_long_term(fake_redis, "A", MemoryItem(id="a", content="A 的事实"))
    await store.upsert_long_term(fake_redis, "B", MemoryItem(id="b", content="B 的事实"))
    assert [m.id for m in await store.get_all_long_term(fake_redis, "A")] == ["a"]
    assert [m.id for m in await store.get_all_long_term(fake_redis, "B")] == ["b"]


# ===== list_objects / turn_count / working_span =====
async def test_list_objects(fake_redis):
    await store.upsert_long_term(fake_redis, "A", MemoryItem(id="a", content="x"))
    await store.upsert_long_term(fake_redis, "B", MemoryItem(id="b", content="y"))
    objs = await store.list_objects(fake_redis)
    assert set(objs) == {"A", "B"}


async def test_turn_count_and_working_span(fake_redis):
    from storage import chat_store
    # 2 轮 = 4 条
    for role, c in [("user", "q1"), ("assistant", "a1"), ("user", "q2"), ("assistant", "a2")]:
        await chat_store.append_message(fake_redis, "u", role, c)
    assert await store.get_turn_count(fake_redis, "u") == 2
    span = await store.get_working_span(fake_redis, "u", turns=1)
    assert len(span) == 2  # 最近 1 轮 = 2 条


# ===== chat_store 向后兼容 + 前缀 =====
async def test_chat_store_append_with_new_fields(fake_redis):
    from storage import chat_store
    await chat_store.append_message(fake_redis, "u", "user", "hi", ts=12345, msg_type="chat", mid="m1")
    hist = await chat_store.get_history(fake_redis, "u")
    assert hist[0].content == "hi"


def test_chat_store_key_has_mychat_prefix():
    from storage import chat_store
    assert chat_store._key("u") == "mychat:chat:u"
