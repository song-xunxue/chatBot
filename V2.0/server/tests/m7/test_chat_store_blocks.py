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
