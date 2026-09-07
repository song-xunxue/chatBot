"""
chat_store block 三层单测:append/get_history/sender→role 映射/UUID mid/
静默分组/roleplay 物理隔离/软删过滤/count_messages。对应 docs/02 §9/§11。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 创建 chat_store block 三层单测

2026-09-07
变更说明：
  1. 新增 ts 驱动块簿记回归(审查修复):归档旧 ts 并入当前块不拆块不倒挂/静默按消息 ts
     判定新块 start_ts=消息 ts/has_history
"""
import time as _time

from storage import chat_store
from llm.base import Message


async def test_append_and_get_history(fake_redis):
    """append 消息 → get_history 转 Message(user/ai→assistant)。
    显式递增 ts 避免同毫秒 ZSet 同 score 排序不稳定(pre-existing flaky)。"""
    base = int(_time.time() * 1000)
    mid_u = await chat_store.append_message(fake_redis, "u1", sender="user", content="你好", ts=base)
    mid_a = await chat_store.append_message(fake_redis, "u1", sender="ai", content="你也好", ts=base + 1)
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


# ================ ts 驱动块簿记(2026-09-07 审查修复回归)================

async def test_archive_old_ts_joins_current_block(fake_redis, monkeypatch):
    """归档写入(旧 ts,如代答队列归档/手动回复)并入当前活跃块:不拆块、end_ts 不回拨
    (防 start_ts>end_ts 倒挂与后续写入被误判静默)"""
    now = int(_time.time() * 1000)
    monkeypatch.setattr(chat_store, "_now_ms", lambda: now)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="新消息", ts=now)
    block1 = await fake_redis.get(chat_store._active_key("u1"))
    # 归档 3 小时前的旧消息(显式旧 ts)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="归档旧消息",
                                    ts=now - 3 * 3600 * 1000)
    assert await fake_redis.get(chat_store._active_key("u1")) == block1   # 同块,不拆
    meta = await fake_redis.hgetall(chat_store._block_key(block1))
    assert int(meta["end_ts"]) == now                                      # end_ts 不回拨
    assert int(meta["start_ts"]) <= int(meta["end_ts"])                    # 无倒挂
    # 后续正常写入仍并入(不被归档的旧 end_ts 误判静默)
    await chat_store.append_message(fake_redis, "u1", sender="ai", content="再聊", ts=now + 1)
    assert await fake_redis.get(chat_store._active_key("u1")) == block1


async def test_silence_split_by_message_ts_new_block_start(fake_redis, monkeypatch):
    """静默判定按消息 ts:间隔超阈开新块,新块 start_ts=该消息 ts(不再统一 now,
    归档场景面板不再出现'刚刚'的假块)"""
    t0 = int(_time.time() * 1000) - 3600 * 1000   # 1 小时前
    monkeypatch.setattr(chat_store, "_now_ms", lambda: t0)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="旧", ts=t0)
    block1 = await fake_redis.get(chat_store._active_key("u1"))
    # 模拟真实时间已过 1 小时,但消息 ts 只前进 11 分钟(归档语义):按消息 ts 判定超阈
    now_real = int(_time.time() * 1000)
    monkeypatch.setattr(chat_store, "_now_ms", lambda: now_real)
    t1 = t0 + 11 * 60 * 1000
    await chat_store.append_message(fake_redis, "u1", sender="user", content="归档", ts=t1)
    block2 = await fake_redis.get(chat_store._active_key("u1"))
    assert block2 != block1                              # 拆块(消息间隔超阈)
    meta = await fake_redis.hgetall(chat_store._block_key(block2))
    assert int(meta["start_ts"]) == t1                   # 新块 start_ts=消息 ts,非 now_real


async def test_clear_queue_archives_into_one_block(fake_redis, monkeypatch):
    """一键清空 N 条旧 ts 消息:不产生 N 个'刚刚'单消息块(全并入当前活跃块)"""
    now = int(_time.time() * 1000)
    monkeypatch.setattr(chat_store, "_now_ms", lambda: now)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="当前", ts=now)
    block1 = await fake_redis.get(chat_store._active_key("u1"))
    for i in range(5):                                   # 归档 5 条半小时前的旧消息
        await chat_store.append_message(fake_redis, "u1", sender="user", content=f"旧{i}",
                                        ts=now - 1800 * 1000 - i)
    assert await fake_redis.get(chat_store._active_key("u1")) == block1   # 仍在同一块
    blocks = await fake_redis.zcard(chat_store._blocks_key("u1"))
    assert blocks == 1                                   # 无块洪水


async def test_has_history(fake_redis):
    """has_history:无历史 False,append 后 True(陌生人门控用)"""
    assert await chat_store.has_history(fake_redis, "u1") is False
    await chat_store.append_message(fake_redis, "u1", sender="user", content="hi")
    assert await chat_store.has_history(fake_redis, "u1") is True


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


async def test_hard_delete_message(fake_redis):
    """真删消息(2026-08-18 软删→物理删,对齐 QQ 删除语义):不进 get_history,存储也移除"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="user", content="删我")
    keep = await chat_store.append_message(fake_redis, "u1", sender="ai", content="留下")
    assert await chat_store.hard_delete_message(fake_redis, mid) is True
    assert await chat_store.get_history(fake_redis, "u1") != []   # 剩余消息不受影响
    assert all(m.content != "删我" for m in await chat_store.get_history(fake_redis, "u1"))
    assert await chat_store.get_message(fake_redis, mid) is None  # 消息 hash 已物理删
    assert await chat_store.hard_delete_message(fake_redis, keep) is True
    assert await chat_store.hard_delete_message(fake_redis, keep) is False   # 再删返 False


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


async def test_list_recent_blocks(fake_redis):
    """跨 object_id 列最近 block(按 start_ts 倒序),含元数据 + msg_count(面板 block 级会话列表,2026-07-05)"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="u1-a")
    await chat_store.append_message(fake_redis, "u2", sender="user", content="u2-a")
    # u1 关当前 block 后再 append → 开新 block(最后开,start_ts 最晚,倒序应在最前)
    bid = await fake_redis.get(chat_store._active_key("u1"))
    await chat_store.close_block(fake_redis, bid)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="u1-b")
    blocks = await chat_store.list_recent_blocks(fake_redis, limit=50)
    assert len(blocks) == 3   # u1×2 + u2×1
    # 最新开的 block 在前(u1 第二个 block)
    assert blocks[0]["object_id"] == "u1"
    assert blocks[0]["msg_count"] == 1
    assert {"block_id", "object_id", "start_ts", "end_ts", "status", "msg_count"} <= set(blocks[0].keys())
    assert {b["object_id"] for b in blocks} == {"u1", "u2"}


async def test_delete_block(fake_redis):
    """物理删单个 block + 其消息(2026-07-05);ai 有 score 联动写 neg 队列"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="hi")
    mid_a = await chat_store.append_message(fake_redis, "u1", sender="ai", content="reply")
    await chat_store.set_score(fake_redis, mid_a, score_base=80, mood_value=0.5, mood_bias=0)
    bid = await fake_redis.get(chat_store._active_key("u1"))
    r = await chat_store.delete_block(fake_redis, bid)
    assert r["deleted_msgs"] == 2
    assert r["neg_linked"] == 1          # ai 有 score → 联动 neg
    # block + 消息物理删
    assert await fake_redis.exists(chat_store._block_key(bid)) == 0
    assert await fake_redis.exists(chat_store._msgs_key(bid)) == 0
    assert await chat_store.list_messages(fake_redis, "u1") == []
    # 从 blocks ZSet 移除 + active 清理
    assert await fake_redis.zcard(chat_store._blocks_key("u1")) == 0
    assert await fake_redis.get(chat_store._active_key("u1")) is None


async def test_delete_object_history(fake_redis):
    """清空该用户全部历史(2026-07-05);其他用户不动"""
    await chat_store.append_message(fake_redis, "u1", sender="user", content="a")
    await chat_store.append_message(fake_redis, "u2", sender="user", content="b")   # 其他用户不受影响
    r = await chat_store.delete_object_history(fake_redis, "u1")
    assert r["deleted_blocks"] == 1
    assert r["deleted_msgs"] == 1
    assert await chat_store.list_messages(fake_redis, "u1") == []
    assert len(await chat_store.list_messages(fake_redis, "u2")) == 1   # u2 保留
