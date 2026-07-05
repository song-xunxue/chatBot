"""
takeover service 代答产出全链路单测:落消息/下发被动优先降级主动/评分记忆心情软失败/批量/TakeoverNotFound。
mock send_c2c_message 控制下发分支;memory_enabled=False 跳过记忆编码(单独用例 mock coordinator)。

作者: 李文煜
日期: 2026-06-30
"""
import httpx
import pytest

from core.config import settings
from storage import takeover_store, chat_store
from takeover import service as takeover_svc


def _http_error(status: int) -> httpx.HTTPStatusError:
    """构造 httpx.HTTPStatusError(send_c2c_message 被动被拒时抛)"""
    req = httpx.Request("POST", "http://x")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError(f"rejected {status}", request=req, response=resp)


async def _noop_send(oid, content, *, msg_id="", msg_seq=1, human_authored=False):
    """默认 mock:下发成功"""
    return {"id": "MSG"}


async def test_takeover_not_found(fake_redis, monkeypatch):
    """空队列 → TakeoverNotFound"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    with pytest.raises(takeover_svc.TakeoverNotFound):
        await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "代答")


async def test_lands_user_proxy_same_block(fake_redis, monkeypatch):
    """代答落 user+proxy 消息同 block(对话连续,user 在前 proxy 在后)"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr("qq.api_client.send_c2c_message", _noop_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="你好", msg_id="mid1")
    await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "代答回复")
    msgs = await chat_store.list_messages(fake_redis, "u1")
    assert [m["sender"] for m in msgs] == ["user", "proxy"]
    assert msgs[1]["source"] == "proxy"


async def test_passive_success(fake_redis, monkeypatch):
    """被动回复成功(msg_id 非空)→ mode=passive"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    sent = []

    async def fake_send(oid, content, *, msg_id="", msg_seq=1, human_authored=False):
        sent.append(msg_id)
        return {"id": "MSG"}
    monkeypatch.setattr("qq.api_client.send_c2c_message", fake_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi", msg_id="MID")
    r = await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert r["delivered"] is True
    assert r["mode"] == "passive"
    assert sent == ["MID"]          # 被动带 msg_id


async def test_passive_rejected_fallback_active(fake_redis, monkeypatch):
    """被动被拒(4xx)→ 降级主动成功 → mode=active"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    calls = []

    async def fake_send(oid, content, *, msg_id="", msg_seq=1, human_authored=False):
        calls.append(msg_id)
        if msg_id:                  # 被动(带 msg_id)被拒
            raise _http_error(400)
        return {"id": "MSG"}        # 主动成功
    monkeypatch.setattr("qq.api_client.send_c2c_message", fake_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi", msg_id="MID")
    r = await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert r["delivered"] is True
    assert r["mode"] == "active"
    assert calls == ["MID", ""]     # 先被动后主动


async def test_both_fail_delivered_false(fake_redis, monkeypatch):
    """被动主动都失败 → delivered=False(消息已落库不回滚)"""
    monkeypatch.setattr(settings, "memory_enabled", False)

    async def fake_send(oid, content, *, msg_id="", msg_seq=1, human_authored=False):
        raise _http_error(400)
    monkeypatch.setattr("qq.api_client.send_c2c_message", fake_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi", msg_id="MID")
    r = await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert r["delivered"] is False
    assert len(await chat_store.list_messages(fake_redis, "u1")) == 2   # 消息仍落库


async def test_score_failure_not_blocking(fake_redis, monkeypatch):
    """评分抛异常不阻塞(消息仍落库 + 下发)"""
    monkeypatch.setattr(settings, "memory_enabled", False)

    async def boom(redis, *a, **k):
        raise RuntimeError("score boom")
    monkeypatch.setattr("score.service.score_reply", boom)
    monkeypatch.setattr("qq.api_client.send_c2c_message", _noop_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi")
    r = await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert r["delivered"] is True


async def test_memory_on_turn_called(fake_redis, monkeypatch):
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
    monkeypatch.setattr("qq.api_client.send_c2c_message", _noop_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="hi")
    await takeover_svc.resolve_and_deliver(fake_redis, "u1", None, "答")
    assert called["n"] == 1


async def test_batch_clears_queue(fake_redis, monkeypatch):
    """批量代答:多条 pending 逐条消费,队列清空"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr("qq.api_client.send_c2c_message", _noop_send)
    await takeover_store.enqueue(fake_redis, "u1", user_text="m1")
    await takeover_store.enqueue(fake_redis, "u1", user_text="m2")
    r = await takeover_svc.resolve_and_deliver_batch(fake_redis, "u1", [{"answer": "a1"}, {"answer": "a2"}])
    assert r["success"] == 2
    assert len(r["results"]) == 2
    assert await takeover_store.list_queue(fake_redis, "u1") == []
