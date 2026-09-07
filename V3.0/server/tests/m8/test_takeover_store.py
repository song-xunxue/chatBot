"""
takeover_store per-object FIFO 队列单测:开关/入队出队/指定pid/孤儿清理/跳过/msg_seq。
对应 docs/02 §8.2。

作者: 李文煜
日期: 2026-06-30

2026-09-07
变更说明:
  1. 新增 drain_queue 用例(FIFO 全出队/status 标记/并发已消费跳过/孤儿清理/自定义 status)
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


async def test_drain_queue_fifo_and_status(fake_redis):
    """drain_queue(2026-09-07):全部出队(FIFO 正序)+ status 标记 manual + 队列清空"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    p2 = await takeover_store.enqueue(fake_redis, "u1", user_text="m2")
    out = await takeover_store.drain_queue(fake_redis, "u1")
    assert [p["pid"] for p in out] == [p1, p2]   # FIFO 正序
    assert out[0]["status"] == "manual"          # 标记(审计可查)
    assert out[0]["user_text"] == "m1"
    assert await takeover_store.list_queue(fake_redis, "u1") == []


async def test_drain_queue_skips_resolved(fake_redis):
    """并发防护:已被 resolve 消费(status!=pending)的 pending 不返回(防双重落库),但仍出队"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    p2 = await takeover_store.enqueue(fake_redis, "u1", user_text="m2")
    await takeover_store.resolve(fake_redis, "u1", p1)   # p1 已被代答消费
    out = await takeover_store.drain_queue(fake_redis, "u1")
    assert [p["pid"] for p in out] == [p2]               # 只剩未消费的 p2


async def test_drain_queue_custom_status(fake_redis):
    """status 参数:一键清空传 cleared"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    out = await takeover_store.drain_queue(fake_redis, "u1", status="cleared")
    assert out[0]["status"] == "cleared"


async def test_drain_queue_cleans_orphans(fake_redis):
    """孤儿 pid(Hash 已过期)不返回,但队列清干净"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    await fake_redis.delete(f"mychat:takeover:pending:u1:{p1}")   # 模拟 TTL 过期
    assert await takeover_store.drain_queue(fake_redis, "u1") == []
    assert await fake_redis.llen("mychat:takeover:queue:u1") == 0


async def test_skip_mark_marks_and_keeps_hash(fake_redis):
    """skip_mark(2026-09-07):命中标记 status=skipped+LREM(不 DEL,详情留 1h 可恢复)"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    assert await takeover_store.skip_mark(fake_redis, "u1", p1) is True
    assert await takeover_store.list_queue(fake_redis, "u1") == []
    pending = await takeover_store.get_pending(fake_redis, "u1", p1)
    assert pending and pending["status"] == "skipped"          # Hash 留存(审计/恢复)


async def test_skip_mark_rejects_consumed(fake_redis):
    """skip_mark 并发防护:已被 resolve/drain 消费(status!=pending)返 False"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    await takeover_store.resolve(fake_redis, "u1", p1)         # 已被代答消费
    assert await takeover_store.skip_mark(fake_redis, "u1", p1) is False


async def test_requeue_restores_fifo(fake_redis):
    """requeue(2026-09-07):drain 出的 pending 回灌,status 重置 pending,FIFO 顺序保持"""
    p1 = await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    p2 = await takeover_store.enqueue(fake_redis, "u1", user_text="m2")
    pendings = await takeover_store.drain_queue(fake_redis, "u1")
    assert await takeover_store.requeue(fake_redis, "u1", pendings) == 2
    q = await takeover_store.list_queue(fake_redis, "u1")
    assert [p["pid"] for p in q] == [p1, p2]                   # FIFO 顺序恢复
    assert all(p["status"] == "pending" for p in q)
