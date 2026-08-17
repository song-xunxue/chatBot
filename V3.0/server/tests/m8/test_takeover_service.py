"""
takeover service 代答产出全链路单测:落消息/下发被动优先降级主动/评分记忆心情软失败/批量/TakeoverNotFound。
mock 层:fake_adapter(adapter 单例注入,2026-08-17 精简版;原 mock qq.api_client 已随官方栈删);
memory_enabled=False 跳过记忆编码(单独用例 mock coordinator)。

作者: 李文煜
日期: 2026-06-30

2026-08-17
变更说明：
  1. V3.0 精简:mock 层从 qq.api_client.send_c2c_message 迁到 fake_adapter(出站统一走 adapter)
"""
import pytest

from core.config import settings
from storage import takeover_store, chat_store
from takeover import service as takeover_svc


async def test_takeover_not_found(fake_redis, monkeypatch):
    """空队列 → TakeoverNotFound"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    with pytest.raises(takeover_svc.TakeoverNotFound):
        await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "代答")


async def test_lands_user_proxy_same_block(fake_redis, monkeypatch, fake_adapter):
    """代答落 user+proxy 消息同 block(对话连续,user 在前 proxy 在后)"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await takeover_store.enqueue(fake_redis, "u1", user_text="你好", msg_id="mid1")
    await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "代答回复")
    msgs = await chat_store.list_messages(fake_redis, "u1")
    assert [m["sender"] for m in msgs] == ["user", "proxy"]
    assert msgs[1]["source"] == "proxy"


async def test_passive_success(fake_redis, monkeypatch, fake_adapter):
    """被动回复成功(msg_id 非空)→ mode=passive"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi", msg_id="MID")
    r = await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert r["delivered"] is True
    assert r["mode"] == "passive"
    assert len(fake_adapter.sent) == 1        # 只发一次(被动成功不降级)
    assert fake_adapter.sent[0][3] == "MID"   # 被动带 msg_id(sent 元组第4位)


async def test_passive_rejected_fallback_active(fake_redis, monkeypatch, fake_adapter):
    """被动被拒 → 降级主动成功 → mode=active"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    _orig = fake_adapter.send_text

    async def _send(oid, content, *, msg_id="", msg_seq=1, human_authored=False):
        if msg_id:                    # 被动(带 msg_id)被拒
            fake_adapter.fail_on = "text"
            try:
                return await _orig(oid, content, msg_id=msg_id, msg_seq=msg_seq, human_authored=human_authored)
            finally:
                fake_adapter.fail_on = None   # 主动重试恢复成功
        return await _orig(oid, content, msg_id=msg_id, msg_seq=msg_seq, human_authored=human_authored)

    fake_adapter.send_text = _send
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi", msg_id="MID")
    r = await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert r["delivered"] is True
    assert r["mode"] == "active"
    assert len(fake_adapter.sent) == 1 and fake_adapter.sent[0][3] == ""   # 被动被拒后,主动(msg_id="")成功


async def test_both_fail_delivered_false(fake_redis, monkeypatch, fake_adapter):
    """被动主动都失败 → delivered=False(消息已落库不回滚)"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    fake_adapter.fail_on = "all"
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi", msg_id="MID")
    r = await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert r["delivered"] is False
    assert len(await chat_store.list_messages(fake_redis, "u1")) == 2   # 消息仍落库


async def test_score_failure_not_blocking(fake_redis, monkeypatch, fake_adapter):
    """评分抛异常不阻塞(消息仍落库 + 下发)"""
    monkeypatch.setattr(settings, "memory_enabled", False)

    async def boom(redis, *a, **k):
        raise RuntimeError("score boom")
    monkeypatch.setattr("score.service.score_reply", boom)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi")
    r = await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert r["delivered"] is True


async def test_memory_on_turn_called(fake_redis, monkeypatch, fake_adapter):
    """memory_enabled=True 时 on_turn_complete 被调(传 MessageContext)"""
    called = {"n": 0}

    class _MockCoord:
        async def on_turn_complete(self, ctx):
            called["n"] += 1
            assert ctx.object_id == "u1"
            assert ctx.user_text == "hi"
            assert ctx.reply_text == "答"

    async def _get_coord():
        return _MockCoord()
    monkeypatch.setattr("memory.coordinator.get_memory_coordinator", _get_coord)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi")
    await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert called["n"] == 1


async def test_batch_clears_queue(fake_redis, monkeypatch, fake_adapter):
    """批量代答:多条 pending 逐条消费,队列清空"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    await takeover_store.enqueue(fake_redis, "u1", user_text="m2")
    r = await takeover_svc.resolve_and_deliver_batch(fake_redis, "u1", [{"answer": "a1"}, {"answer": "a2"}])
    assert r["success"] == 2
    assert len(r["results"]) == 2
    assert await takeover_store.list_queue(fake_redis, "u1") == []


async def test_send_proactive(fake_redis, monkeypatch, fake_adapter):
    """主动发送(2026-07-05):不依赖 pending,落 proxy 消息 + 下发主动(msg_id 空)→ mode=active"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    r = await takeover_svc.send_proactive(fake_redis, "u1", "主动推话")
    assert r["delivered"] is True
    assert r["mode"] == "active"          # 主动(msg_id 空)
    assert len(fake_adapter.sent) == 1
    assert fake_adapter.sent[0][3] == ""            # 主动 msg_id=""
    assert fake_adapter.sent[0][5] is True          # human_authored=True(admin 手打跳过守卫)
    # 落 proxy 消息进 live 历史
    msgs = await chat_store.list_messages(fake_redis, "u1")
    assert len(msgs) == 1
    assert msgs[0]["sender"] == "proxy"
    assert msgs[0]["content"] == "主动推话"
    # 主动发无 user 回合(不落 user 消息)
    assert all(m["sender"] != "user" for m in msgs)
