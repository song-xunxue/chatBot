"""
takeover_store per-object FIFO 队列单测:开关/入队出队/指定pid/孤儿清理/跳过/msg_seq。
对应 docs/02 §8.2。

作者: 李文煜
日期: 2026-06-30
"""
from storage import takeover_store


async def test_enabled_toggle(fake_redis):
    """set/is_enabled 开关"""
    assert await takeover_store.is_enabled(fake_redis, "u1") is False
    await takeover_store.set_enabled(fake_redis, "u1", True)
    assert await takeover_store.is_enabled(fake_redis, "u1") is True
    await takeover_store.set_enabled(fake_redis, "u1", False)
    assert await takeover_store.is_enabled(fake_redis, "u1") is False


async def test_enqueue_and_list_fifo(fake_redis):
    """入队 FIFO 顺序(list_queue 正序,队首在前)"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg1", msg_id="mid1")
    p2 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg2", msg_id="mid2")
    q = await takeover_store.list_queue(fake_redis, "u1")
    assert [p["pid"] for p in q] == [p1, p2]   # FIFO 正序,队首在前
    assert q[0]["user_text"] == "msg1"
    assert q[0]["msg_id"] == "mid1"
    assert await takeover_store.queue_length(fake_redis, "u1") == 2


async def test_resolve_head(fake_redis):
    """resolve(pid=None) 取队首 + 出队 + status=resolved"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg1")
    p2 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg2")
    pending = await takeover_store.resolve(fake_redis, "u1", None)
    assert pending["pid"] == p1                 # 队首
    assert pending["status"] == "resolved"
    assert [p["pid"] for p in await takeover_store.list_queue(fake_redis, "u1")] == [p2]


async def test_resolve_by_pid(fake_redis):
    """resolve(指定 pid) 跳序出队(LREM 精确移除)"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg1")
    p2 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg2")
    pending = await takeover_store.resolve(fake_redis, "u1", p2)   # 直接答 p2(非队首)
    assert pending["pid"] == p2
    assert [p["pid"] for p in await takeover_store.list_queue(fake_redis, "u1")] == [p1]


async def test_resolve_empty_returns_none(fake_redis):
    """空队列 resolve 返回 None"""
    assert await takeover_store.resolve(fake_redis, "u1", None) is None


async def test_resolve_expired_pid_returns_none(fake_redis):
    """指定 pid 已过期(Hash TTL 失效)→ 清孤儿返 None"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg1")
    await fake_redis.delete(f"mychat:takeover:pending:u1:{p1}")   # 模拟 TTL 过期
    assert await takeover_store.resolve(fake_redis, "u1", p1) is None
    assert await takeover_store.list_queue(fake_redis, "u1") == []   # 孤儿已清


async def test_list_queue_filters_orphan(fake_redis):
    """list_queue 过滤过期孤儿 pid"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg1")
    p2 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg2")
    await fake_redis.delete(f"mychat:takeover:pending:u1:{p1}")   # p1 过期成孤儿
    q = await takeover_store.list_queue(fake_redis, "u1")
    assert [p["pid"] for p in q] == [p2]        # 孤儿 p1 被过滤


async def test_resolve_purges_orphan_head(fake_redis):
    """resolve(队首) 先清连续孤儿头,取到首个活 pending"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg1")
    p2 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg2")
    await fake_redis.delete(f"mychat:takeover:pending:u1:{p1}")   # 队首 p1 过期
    pending = await takeover_store.resolve(fake_redis, "u1", None)
    assert pending["pid"] == p2                 # 跳过孤儿 p1,取 p2


async def test_skip(fake_redis):
    """skip 跳过(出队 + 删 pending)"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg1")
    assert await takeover_store.skip(fake_redis, "u1", p1) is True
    assert await takeover_store.list_queue(fake_redis, "u1") == []
    assert await takeover_store.skip(fake_redis, "u1", p1) is False   # 已删


async def test_next_msg_seq_increments(fake_redis):
    """msg_seq per-oid 递增,不同 oid 独立"""
    assert await takeover_store.next_msg_seq(fake_redis, "u1") == 1
    assert await takeover_store.next_msg_seq(fake_redis, "u1") == 2
    assert await takeover_store.next_msg_seq(fake_redis, "u2") == 1


async def test_mark_delivered(fake_redis):
    """mark_delivered 回写交付状态"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="msg1")
    await takeover_store.mark_delivered(fake_redis, "u1", p1, {"delivered": True, "mode": "passive"})
    pending = await takeover_store.get_pending(fake_redis, "u1", p1)
    assert pending["delivered"] == "1"
    assert pending["deliver_mode"] == "passive"
