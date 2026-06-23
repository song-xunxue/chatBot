"""
forget_tick 遗忘批处理集成测试（M3-review 补 high test gap）
验证软遗忘、locked/important 保留、上限淘汰、对象隔离、空对象、手动遗忘不存在返回 False

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3-review 补 forget_tick 全链路测试（此前零覆盖）
"""
from memory import store
from memory.models import MemoryItem


async def test_forget_tick_marks_low_retain(coord, fake_redis):
    import time
    now_ms = int(time.time() * 1000)
    # created_ts 取新值避免物理清理；last_access_ts=1（老）触发软遗忘
    await store.upsert_long_term(fake_redis, "u", MemoryItem(
        id="m1", content="x", importance=0.1, emotion=0.0,
        access_count=0, created_ts=now_ms, last_access_ts=1))
    marked = await coord.forget_tick()
    assert marked >= 1
    assert (await store.get_long_term(fake_redis, "u", "m1")).forgotten is True


async def test_forget_tick_keeps_locked(coord, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(
        id="lo", content="x", importance=0.0, locked=True, created_ts=1, last_access_ts=1))
    await coord.forget_tick()
    assert (await store.get_long_term(fake_redis, "u", "lo")).forgotten is False


async def test_forget_tick_keeps_important(coord, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(
        id="hi", content="x", importance=0.9, created_ts=1, last_access_ts=1))
    await coord.forget_tick()
    assert (await store.get_long_term(fake_redis, "u", "hi")).forgotten is False


async def test_forget_tick_object_isolation(coord, fake_redis):
    import time
    now_ms = int(time.time() * 1000)
    await store.upsert_long_term(fake_redis, "A",
        MemoryItem(id="a1", content="x", importance=0.1, created_ts=now_ms, last_access_ts=1))
    await store.upsert_long_term(fake_redis, "B",
        MemoryItem(id="b1", content="x", importance=0.1, created_ts=now_ms, last_access_ts=1))
    marked = await coord.forget_tick()
    assert marked == 2
    assert (await store.get_long_term(fake_redis, "A", "a1")).forgotten is True
    assert (await store.get_long_term(fake_redis, "B", "b1")).forgotten is True


async def test_forget_tick_no_objects_returns_zero(coord, fake_redis):
    assert await coord.forget_tick() == 0


async def test_forget_tick_evict_over_max(coord, fake_redis, monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "memory_longterm_max_facts", 2)
    # 3 条高 retain（不被软遗忘），超上限淘汰最低 retain
    for i in range(3):
        await store.upsert_long_term(fake_redis, "u", MemoryItem(
            id=f"m{i}", content=f"x{i}", importance=0.9,
            access_count=5, created_ts=1, last_access_ts=1))
    await coord.forget_tick()
    active = await store.get_all_long_term(fake_redis, "u", include_forgotten=False)
    assert len(active) <= 2  # 上限淘汰生效


async def test_manual_forget_restore_nonexistent_false(coord, fake_redis):
    assert await coord.manual_forget("u", "ghost") is False
    assert await coord.restore("u", "ghost") is False


async def test_record_negative_feedback_writes_pending(coord, fake_redis):
    """F-C-09 负样本：删除消息经 record_negative_feedback 记入 persona pending 队列"""
    from persona import store as persona_store
    await persona_store.get_default_persona(fake_redis)  # seed 默认人设
    await coord.record_negative_feedback(
        "u_del", {"reason": "out_of_character", "msg_id": "m1"})
    pid = await persona_store.get_object_persona_id(fake_redis, "u_del")
    pending = await store.list_pending(fake_redis, pid)
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"
    assert pending[0]["payload"]["reason"] == "out_of_character"
    assert pending[0]["source"] == "u_del"


async def test_forget_tick_physically_purges_old_forgotten(coord, fake_redis):
    """物理清理：很老且 forgotten 的条目被真正删除（get 返回 None）"""
    import time
    now = int(time.time() * 1000)
    old_ts = now - 999_999_999_999  # 远超保留期（retain_ms = halflife*10 ≈ 30 天）
    await store.upsert_long_term(fake_redis, "u", MemoryItem(
        id="old", content="x", importance=0.1, forgotten=True,
        created_ts=old_ts, last_access_ts=old_ts))
    await coord.forget_tick()
    assert await store.get_long_term(fake_redis, "u", "old") is None  # 物理删除
