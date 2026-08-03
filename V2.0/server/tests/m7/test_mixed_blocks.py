"""
list_recent_blocks 混合 chat+roleplay 单测(2026-07-07 拟人化 UI 合并):
chat 真实 block + roleplay 训练 block 混合返回,带 source 字段(real/training)区分,
供对话历史页混合展示(训练样本并入对话历史)。

作者: 李文煜
日期: 2026-07-07
"""
from storage import chat_store


async def test_list_recent_blocks_mixed_sources(fake_redis):
    """chat + roleplay block 混合返回,带 source 区分"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="真实对话")
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="训练样本")
    blocks = await chat_store.list_recent_blocks(fake_redis, limit=50)
    assert len(blocks) >= 2
    sources = {b["source"] for b in blocks}
    assert "real" in sources
    assert "training" in sources
    assert all("source" in b for b in blocks)   # 每条都有 source


async def test_list_recent_blocks_real_meta(fake_redis):
    """real block 元数据正确(object_id/msg_count)"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="hi")
    blocks = await chat_store.list_recent_blocks(fake_redis)
    real = [b for b in blocks if b["source"] == "real"]
    assert len(real) == 1
    assert real[0]["msg_count"] >= 1
    assert real[0]["object_id"] == "u1"


async def test_list_recent_blocks_training_meta(fake_redis):
    """training block 元数据正确"""
    await chat_store.append_roleplay_message(fake_redis, "u1", role="user", content="rp")
    blocks = await chat_store.list_recent_blocks(fake_redis)
    train = [b for b in blocks if b["source"] == "training"]
    assert len(train) == 1
    assert train[0]["msg_count"] >= 1


async def test_list_recent_blocks_empty(fake_redis):
    """无 block → 空列表"""
    assert await chat_store.list_recent_blocks(fake_redis) == []
