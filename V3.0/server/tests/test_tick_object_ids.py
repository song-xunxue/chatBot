"""
on_tick 活跃对象源 tick_object_ids 的单元测试(main.py 2026-10-25 集成 bug 修复配套)

覆盖:最近会话 ∪ mood oids 并集口径、非数字 oid 过滤(debug 日志)、空库返回空、
单数据源故障时降级用另一源。

作者: 李文煜
日期: 2026-10-25

2026-10-25
变更说明：
  1. 新建:验证真实私聊未命中 mood 情感词(仅有聊天 block)也能进 tick 活跃源,
     以及 seed 的 demo 等非数字 oid 被跳过(不再触发 onebot int(oid) invalid literal)
"""
import logging

from main import tick_object_ids
from mood import service as mood_service
from storage import chat_store


async def _make_blocks(redis, oid: str) -> None:
    """用 chat_store 公开 API 造一个会话 block(等价于该 oid 最近有消息)"""
    await chat_store.open_or_get_block(redis, oid)


async def test_union_of_recent_sessions_and_mood(fake_redis):
    # 2690468347 只有聊天 block、从无 mood 记录;88888 只在 mood oids;777 两源都在(去重)
    await _make_blocks(fake_redis, "2690468347")
    await _make_blocks(fake_redis, "777")
    await fake_redis.sadd("mychat:mood:oids", "88888", "777")
    assert await tick_object_ids(fake_redis) == ["2690468347", "777", "88888"]


async def test_non_numeric_skipped_with_debug_log(fake_redis, caplog):
    # seed 的 demo/demo2_alice 等非数字 oid 不能下发 QQ,应跳过并留 debug 日志;
    # ²/２(Unicode 上标/全角数字)能过 isdigit 却过不了 int(),须一并排除
    await _make_blocks(fake_redis, "demo2_alice")
    await fake_redis.sadd("mychat:mood:oids", "demo", "²", "２")
    with caplog.at_level(logging.DEBUG, logger="main"):
        assert await tick_object_ids(fake_redis) == []
    joined = " ".join(caplog.messages)
    assert "demo" in joined and "demo2_alice" in joined


async def test_empty_sources_returns_empty(fake_redis):
    # 全新 Redis(无会话无 mood)→ 空列表,tick 空转不报错
    assert await tick_object_ids(fake_redis) == []


async def test_recent_sessions_failure_degrades_to_mood(fake_redis, monkeypatch):
    # 活跃源 1 故障:降级用 mood oids,调度器不停摆
    async def _boom(*args, **kwargs):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(chat_store, "list_recent_sessions", _boom)
    await fake_redis.sadd("mychat:mood:oids", "123456")
    assert await tick_object_ids(fake_redis) == ["123456"]


async def test_mood_failure_degrades_to_recent_sessions(fake_redis, monkeypatch):
    # 活跃源 2 故障:降级用最近会话
    async def _boom(*args, **kwargs):
        raise RuntimeError("smembers failed")

    monkeypatch.setattr(mood_service, "list_mood_objects", _boom)
    await _make_blocks(fake_redis, "654321")
    assert await tick_object_ids(fake_redis) == ["654321"]
