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


# —— 2026-07-05 多会话 + 评分联动反推 ——

async def test_append_with_score_links_sample(fake_redis):
    """append assistant + 高分 → msg.score + 联动 pos 样本队列(驱动反推);中性分不进队列"""
    await chat_store.append_roleplay_message(
        fake_redis, "u1", role="assistant", content="好回复", score_base=88)
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert rps[0]["score"] == "88"
    assert len(await fake_redis.lrange("mychat:score:pos:u1", 0, -1)) == 1   # 88≥85 → pos
    # 中性分 70 不进任何队列
    await chat_store.append_roleplay_message(
        fake_redis, "u1", role="assistant", content="中回复", score_base=70)
    assert len(await fake_redis.lrange("mychat:score:pos:u1", 0, -1)) == 1
    assert len(await fake_redis.lrange("mychat:score:neg:u1", 0, -1)) == 0


async def test_user_score_not_linked(fake_redis):
    """user 角色评分不联动样本队列(仅 assistant 才有反推意义)"""
    await chat_store.append_roleplay_message(
        fake_redis, "u1", role="user", content="用户消息", score_base=90)
    assert len(await fake_redis.lrange("mychat:score:pos:u1", 0, -1)) == 0


async def test_new_roleplay_block(fake_redis):
    """新建会话:关当前 open + 开新 block;后续 append 进新会话"""
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="会话1")
    b1 = await fake_redis.get(chat_store._rp_active_key("u1"))
    new_block = await chat_store.new_roleplay_block(fake_redis, "u1")
    assert new_block["block_id"] != b1
    assert new_block["status"] == "open"
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="会话2")
    b2 = await fake_redis.get(chat_store._rp_active_key("u1"))
    assert b2 == new_block["block_id"]   # 新消息进新会话


async def test_list_roleplay_blocks(fake_redis):
    """列会话(block 元数据 + msg_count,倒序最近在前)"""
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="a")
    await chat_store.new_roleplay_block(fake_redis, "u1")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="b")
    blocks = await chat_store.list_roleplay_blocks(fake_redis, "u1")
    assert len(blocks) == 2
    assert all("msg_count" in b for b in blocks)
    assert blocks[0]["msg_count"] == 1   # 最近会话(第二个)在前,各 1 条


async def test_list_roleplay_by_block(fake_redis):
    """list_roleplay block_id 过滤:只列选中会话"""
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="s1")
    await chat_store.new_roleplay_block(fake_redis, "u1")   # 关 block1 开 block2
    b2 = await fake_redis.get(chat_store._rp_active_key("u1"))
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="s2")
    rps = await chat_store.list_roleplay(fake_redis, "u1", block_id=b2)
    assert [r["content"] for r in rps] == ["s2"]            # 仅该会话
    assert len(await chat_store.list_roleplay(fake_redis, "u1")) == 2   # 跨所有


async def test_set_roleplay_score(fake_redis):
    """改分:msg.score 更新 + 样本队列调整(旧移除新归类)"""
    mid = await chat_store.append_roleplay_message(
        fake_redis, "u1", role="assistant", content="回复", score_base=88)
    assert len(await fake_redis.lrange("mychat:score:pos:u1", 0, -1)) == 1
    r = await chat_store.set_roleplay_score(fake_redis, "u1", mid, 30)   # 改低分
    assert r["score"] == 30
    assert len(await fake_redis.lrange("mychat:score:pos:u1", 0, -1)) == 0   # pos 清
    assert len(await fake_redis.lrange("mychat:score:neg:u1", 0, -1)) == 1   # neg 加
    rps = await chat_store.list_roleplay(fake_redis, "u1")
    assert rps[0]["score"] == "30"
    assert await chat_store.set_roleplay_score(fake_redis, "u1", "rp_none", 50) is None   # 不存在


async def test_delete_roleplay_block(fake_redis):
    """删整个 roleplay 会话:block + 其消息物理删 + 清 score 样本(2026-07-06)"""
    # 会话1:1 条评分回复(联动 pos 样本)
    await chat_store.append_roleplay_message(
        fake_redis, "u1", role="assistant", content="评分回复", score_base=88)
    b1 = await fake_redis.get(chat_store._rp_active_key("u1"))
    assert len(await fake_redis.lrange("mychat:score:pos:u1", 0, -1)) == 1
    await chat_store.new_roleplay_block(fake_redis, "u1")   # 关 b1 开 b2(使 b1 非 active)
    # 删会话1
    r = await chat_store.delete_roleplay_block(fake_redis, b1)
    assert r["deleted_msgs"] == 1
    assert await fake_redis.exists(chat_store._rp_block_key(b1)) == 0
    assert await fake_redis.exists(chat_store._rp_msgs_key(b1)) == 0
    assert len(await fake_redis.lrange("mychat:score:pos:u1", 0, -1)) == 0   # pos 样本已清
    # 会话2 仍在
    assert len(await chat_store.list_roleplay_blocks(fake_redis, "u1")) == 1
    # 删不存在 block → deleted_msgs:0
    assert (await chat_store.delete_roleplay_block(fake_redis, "rp_nonexistent"))["deleted_msgs"] == 0
