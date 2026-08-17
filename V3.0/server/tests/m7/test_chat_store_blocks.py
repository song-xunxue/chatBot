"""
chat_store.list_blocks 单测(M7):block 第一层浏览。
测空会话/单 block(含 msg_count)/多 block 倒序/limit 截断。

作者: 李文煜
日期: 2026-06-30
"""
import time as _time

from storage import chat_store


async def test_list_blocks_empty(fake_redis):
    """无消息 → 空 block 列表"""
    assert await chat_store.list_blocks(fake_redis, "u1") == []


async def test_list_blocks_single_block_with_msgcount(fake_redis):
    """同一静默窗的消息归一个 block,附 msg_count"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="a")
    await chat_store.append_message(fake_redis, "u1", sender="ai", content="b")
    blocks = await chat_store.list_blocks(fake_redis, "u1")
    assert len(blocks) == 1
    b = blocks[0]
    assert b["object_id"] == "u1"
    assert b["status"] == "open"
    assert b["msg_count"] == 2
    assert "start_ts" in b and "end_ts" in b


async def test_list_blocks_multiple_desc(fake_redis, monkeypatch):
    """静默超阈值产生多 block,列出的顺序为最近在前(倒序)"""
    t0 = _time.time() * 1000
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0))
    await chat_store.append_message(fake_redis, "u1", sender="user", content="旧")
    block_old = await fake_redis.get(chat_store._active_key("u1"))
    # 前进 11 分钟(超 block_silence_min=10)→ 开新 block
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0 + 11 * 60 * 1000))
    await chat_store.append_message(fake_redis, "u1", sender="user", content="新")
    block_new = await fake_redis.get(chat_store._active_key("u1"))
    blocks = await chat_store.list_blocks(fake_redis, "u1")
    assert len(blocks) == 2
    assert blocks[0]["block_id"] == block_new   # 最近在前
    assert blocks[1]["block_id"] == block_old


async def test_list_blocks_limit(fake_redis, monkeypatch):
    """limit 截断:只返回最近 N 个 block"""
    t0 = _time.time() * 1000
    for i in range(3):
        ts = int(t0 + i * 11 * 60 * 1000)   # 每次 >10 分钟,各开新 block
        monkeypatch.setattr(chat_store, "_now_ms", lambda ts=ts: ts)
        await chat_store.append_message(fake_redis, "u1", sender="user", content=f"b{i}")
    blocks = await chat_store.list_blocks(fake_redis, "u1", limit=2)
    assert len(blocks) == 2


async def test_list_recent_sessions_empty(fake_redis):
    """无会话 → 空列表"""
    assert await chat_store.list_recent_sessions(fake_redis) == []


async def test_list_recent_sessions_multi_desc(fake_redis, monkeypatch):
    """多会话按最近 block 的 start_ts 倒序,含 object_id/last_ts/block_count"""
    t0 = _time.time() * 1000
    # u1 先活跃(1 block,start=t0)
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0))
    await chat_store.append_message(fake_redis, "u1", sender="user", content="u1旧")
    # u2 后活跃(更近,start=t0+5min)
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0 + 5 * 60 * 1000))
    await chat_store.append_message(fake_redis, "u2", sender="user", content="u2")
    # u1 又活跃(超 10min 静默 → 开新 block,共 2 blocks,最近 start=t0+20min)
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0 + 20 * 60 * 1000))
    await chat_store.append_message(fake_redis, "u1", sender="user", content="u1最新")
    sessions = await chat_store.list_recent_sessions(fake_redis)
    # 倒序:u1(最近) 在前,u2 在后
    assert [s["object_id"] for s in sessions] == ["u1", "u2"]
    u1 = next(s for s in sessions if s["object_id"] == "u1")
    u2 = next(s for s in sessions if s["object_id"] == "u2")
    assert u1["block_count"] == 2 and u2["block_count"] == 1
    assert u1["last_ts"] > u2["last_ts"]


async def test_list_recent_sessions_limit(fake_redis, monkeypatch):
    """limit 截断"""
    t0 = _time.time() * 1000
    for i in range(3):
        ts = int(t0 + i * 11 * 60 * 1000)
        monkeypatch.setattr(chat_store, "_now_ms", lambda ts=ts: ts)
        await chat_store.append_message(fake_redis, f"u{i}", sender="user", content="x")
    assert len(await chat_store.list_recent_sessions(fake_redis, limit=2)) == 2
