"""
roleplay block 三层单测:append/batch/list/close/update/delete + 物理隔离铁律。
对应 docs/02 §9.2(roleplay block 键)/§12.3。

作者: 李文煜
日期: 2026-06-30
"""
from storage import chat_store


async def test_append_same_open_block(fake_redis):
    """append 进同一 open roleplay block(不静默关 block;显式递增 ts 避免同毫秒排序不稳定)"""
    base = 1000
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="a", ts=base)
    await chat_store.append_roleplay_message(fake_redis, "u1", role="assistant", content="b", ts=base + 1)
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert len(rps) == 2
    assert rps[0]["block_id"] == rps[1]["block_id"]   # 同 block
    assert rps[0]["role"] == "user"


async def test_batch_same_block(fake_redis):
    """批量录入同 block(显式递增 ts 避免同毫秒排序不稳定)"""
    base = 1000
    mids = await chat_store.append_roleplay_batch(fake_redis, "u1", items=[
        {"role": "user", "content": "q1", "ts": base},
        {"role": "assistant", "content": "a1", "ts": base + 1},
    ])
    assert len(mids) == 2
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert rps[0]["block_id"] == rps[1]["block_id"]
    assert [r["content"] for r in rps] == ["q1", "a1"]   # ts 递增 → 正序稳定


async def test_list_ts_order(fake_redis):
    """list 按 ts 正序"""
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="first", ts=100)
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="second", ts=200)
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert [r["content"] for r in rps] == ["first", "second"]


async def test_close_roleplay_block_opens_new(fake_redis):
    """close 后新 append 进新 block(手动分段)"""
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="act1")
    await chat_store.close_roleplay_block(fake_redis, "u1", reason="第一幕完")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="act2")
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert rps[0]["block_id"] != rps[1]["block_id"]   # 不同 block


async def test_update_hset(fake_redis):
    """update 走 hset(改后 list 反映 + status=edited);不存在返 False"""
    mid = await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="原文")
    assert await chat_store.update_roleplay(fake_redis, "u1", mid, "改后") is True
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert rps[0]["content"] == "改后"
    assert rps[0]["status"] == "edited"
    assert await chat_store.update_roleplay(fake_redis, "u1", "rp_nonexistent", "x") is False


async def test_delete_writes_neg(fake_redis):
    """delete 物理删(ZREM+DEL)+ 写 neg 队列"""
    mid = await chat_store.append_roleplay_message(fake_redis, "u1", role="assistant", content="该删")
    assert await chat_store.delete_roleplay(fake_redis, "u1", mid) is True
    assert await chat_store.list_roleplay(fake_redis, "u1") == []
    neg = await fake_redis.lrange(chat_store._roleplay_neg_key("u1"), 0, -1)
    assert len(neg) == 1
    assert await chat_store.delete_roleplay(fake_redis, "u1", mid) is False   # 已删


async def test_isolation_from_history(fake_redis):
    """roleplay 绝不进 get_history(物理隔离铁律)"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="真实聊天")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="训练样本")
    history = await chat_store.get_history(fake_redis, "u1")
    assert all("训练样本" not in m.content for m in history)
    assert len(history) == 1
    assert (await chat_store.list_roleplay(fake_redis, "u1"))[0]["content"] == "训练样本"
