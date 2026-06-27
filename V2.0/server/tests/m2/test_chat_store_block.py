"""
chat_store block 三层单测:append/get_history/sender→role 映射/UUID mid/
静默分组/roleplay 物理隔离/软删过滤/count_messages。对应 docs/02 §9/§11。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 创建 chat_store block 三层单测
"""
import time as _time

from storage import chat_store
from llm.base import Message


async def test_append_and_get_history(fake_redis):
    """append 消息 → get_history 转 Message(user/ai→assistant)"""
    mid_u = await chat_store.append_message(fake_redis, "u1", sender="user", content="你好")
    mid_a = await chat_store.append_message(fake_redis, "u1", sender="ai", content="你也好")
    assert mid_u != mid_a   # UUID mid 唯一
    history = await chat_store.get_history(fake_redis, "u1")
    assert history == [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你也好"),   # ai → assistant
    ]


async def test_empty_history(fake_redis):
    """无消息返回空"""
    assert await chat_store.get_history(fake_redis, "u1") == []


async def test_silence_opens_new_block(fake_redis, monkeypatch):
    """静默超 block_silence_min → 关旧 block 开新 block(docs/02 §6)"""
    t0 = _time.time() * 1000
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0))
    await chat_store.append_message(fake_redis, "u1", sender="user", content="旧block")
    block1 = await fake_redis.get(chat_store._active_key("u1"))
    # 时间前进 11 分钟(超 block_silence_min=10)
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0 + 11 * 60 * 1000))
    block = await chat_store.open_or_get_block(fake_redis, "u1")
    assert block["block_id"] != block1
    assert block["status"] == "open"
    # 旧 block 已关闭
    old = await fake_redis.hgetall(chat_store._block_key(block1))
    assert old["status"] == "closed"
    assert old["close_reason"] == "silence"


async def test_same_block_within_silence(fake_redis, monkeypatch):
    """静默未超阈值 → 同一 block"""
    t0 = _time.time() * 1000
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0))
    await chat_store.append_message(fake_redis, "u1", sender="user", content="a")
    block1 = await fake_redis.get(chat_store._active_key("u1"))
    # 前进 1 分钟(未超 10 分钟)
    monkeypatch.setattr(chat_store, "_now_ms", lambda: int(t0 + 60 * 1000))
    await chat_store.append_message(fake_redis, "u1", sender="user", content="b")
    block2 = await fake_redis.get(chat_store._active_key("u1"))
    assert block1 == block2   # 同 block


async def test_roleplay_isolation(fake_redis):
    """roleplay 样本绝不进 get_history(物理隔离铁律)"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="真实聊天")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="训练样本")
    history = await chat_store.get_history(fake_redis, "u1")
    assert all("训练样本" not in m.content for m in history)
    assert len(history) == 1
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert len(rps) == 1
    assert rps[0]["content"] == "训练样本"


async def test_soft_delete_filtered_from_history(fake_redis):
    """软删消息不进 get_history(但保留在存储)"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="user", content="删我")
    await chat_store.delete_message(fake_redis, mid)
    assert await chat_store.get_history(fake_redis, "u1") == []
    # 消息仍存在(软删,非物理删)
    msg = await chat_store.get_message(fake_redis, mid)
    assert msg["status"] == "deleted"


async def test_count_messages(fake_redis):
    """跨 block 消息总数"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="a")
    await chat_store.append_message(fake_redis, "u1", sender="ai", content="b")
    assert await chat_store.count_messages(fake_redis, "u1") == 2


async def test_get_history_max_messages(fake_redis):
    """get_history 二次裁剪到 max_messages"""
    base = int(_time.time() * 1000)
    for i in range(5):
        await chat_store.append_message(fake_redis, "u1", sender="user", content=f"m{i}", ts=base + i)
    history = await chat_store.get_history(fake_redis, "u1", max_messages=2)
    assert len(history) == 2
    assert history[-1].content == "m4"   # 取最近


async def test_roleplay_update_delete(fake_redis):
    """roleplay 改/删 + 删除写 neg 队列"""
    mid = await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="原文")
    assert await chat_store.update_roleplay(fake_redis, "u1", mid, "改后") is True
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert rps[0]["content"] == "改后"
    assert await chat_store.delete_roleplay(fake_redis, "u1", mid) is True
    assert await chat_store.list_roleplay(fake_redis, "u1") == []
    # neg 队列有记录
    neg = await fake_redis.lrange(chat_store._roleplay_neg_key("u1"), 0, -1)
    assert len(neg) == 1
