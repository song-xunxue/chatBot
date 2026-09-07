"""
takeover service 代答产出全链路单测:落消息/下发被动优先降级主动/评分记忆心情软失败/批量/TakeoverNotFound。
mock 层:fake_adapter(adapter 单例注入,2026-08-17 精简版;原 mock qq.api_client 已随官方栈删);
memory_enabled=False 跳过记忆编码(单独用例 mock coordinator)。

作者: 李文煜
日期: 2026-06-30

2026-08-17
变更说明：
  1. V3.0 精简:mock 层从 qq.api_client.send_c2c_message 迁到 fake_adapter(出站统一走 adapter)

2026-09-07
变更说明：
  1. 新增 record_manual_reply 用例(drain+合并落库+恒正样本+不下发/无pending仅落库/LLM失败仍正样本/
     记忆编码)+ skip_and_archive(归档/并发落空不双写)+ clear_queue(逐条归档)
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


# ================ 手动回复记录 record_manual_reply(2026-09-07)================

async def test_record_manual_reply_full_chain(fake_redis, monkeypatch, fake_adapter, make_provider):
    """手动回复全链:drain 全部 pending → 用户消息合并(同防抖语义)+ 手动回复落库(source=manual)
    → 恒正样本(source=manual, score=100,LLM 打 62 中性分也不进 neg)→ 绝不下发 QQ(已手动发出)"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    # 评分 provider mock:故意打 62(中性区间)验证恒正不参与 classify
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    provider = make_provider('{"score": 62, "reason": "短"}')
    monkeypatch.setattr("score.service.resolve_provider", lambda *a, **k: provider)
    from mood import service as mood_service
    await mood_service.seed_default_kinds(fake_redis)
    await mood_service.set_mood(fake_redis, "10001", 0.5)

    await takeover_store.enqueue(fake_redis, "10001", user_text="在吗", msg_id="m1")
    await takeover_store.enqueue(fake_redis, "10001", user_text="怎么了", msg_id="m2")
    r = await takeover_svc.record_manual_reply(fake_redis, "10001", "嗯嗯在的~", sent_ts=2000)
    assert r["archived_pendings"] == 2 and r["scored"] is True
    assert await takeover_store.list_queue(fake_redis, "10001") == []       # 队列已消化
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert [m["sender"] for m in msgs] == ["user", "proxy"]                 # 合并 user + 手动回复
    assert msgs[0]["content"] == "在吗\n怎么了"                              # 连发合并(同防抖)
    assert msgs[1]["content"] == "嗯嗯在的~"
    assert msgs[1]["source"] == "manual"
    # 恒正样本:62 中性分仍收正样本 score=100;neg 空
    from score import service as score_service
    pos = await score_service.list_samples(fake_redis, "10001", "positive")
    assert len(pos) == 1 and pos[0]["source"] == "manual" and pos[0]["score"] == 100
    assert await score_service.list_samples(fake_redis, "10001", "negative") == []
    assert fake_adapter.sent == []                                          # 绝不下发(已手动发出)


async def test_record_manual_reply_no_pending(fake_redis, monkeypatch, fake_adapter):
    """无 pending(自动模式手动插话/队列已清):仅落 proxy 消息,不评分不记忆不下发"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    r = await takeover_svc.record_manual_reply(fake_redis, "10001", "手动插话", sent_ts=1000)
    assert r["archived_pendings"] == 0 and r["scored"] is False
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert len(msgs) == 1 and msgs[0]["sender"] == "proxy" and msgs[0]["source"] == "manual"
    assert fake_adapter.sent == []


async def test_record_manual_reply_llm_fail_still_positive(fake_redis, monkeypatch, fake_adapter):
    """LLM 评分失败(无 provider,根 conftest 已清 key):四元组无,但恒正样本仍收(黄金标准不依赖 LLM)"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await takeover_store.enqueue(fake_redis, "10001", user_text="hi")
    r = await takeover_svc.record_manual_reply(fake_redis, "10001", "答", sent_ts=2000)
    assert r["scored"] is True
    from score import service as score_service
    pos = await score_service.list_samples(fake_redis, "10001", "positive")
    assert len(pos) == 1 and pos[0]["source"] == "manual" and pos[0]["score"] == 100


async def test_record_manual_reply_memory_encoded(fake_redis, monkeypatch, fake_adapter):
    """有 pending 时记忆编码被调(await_memory=True,同代答链路)"""
    called = {"n": 0}

    class _MockCoord:
        async def on_turn_complete(self, ctx):
            called["n"] += 1
            assert ctx.object_id == "10001"
            assert ctx.reply_text == "手动回"

    async def _get_coord():
        return _MockCoord()
    monkeypatch.setattr("memory.coordinator.get_memory_coordinator", _get_coord)
    await takeover_store.enqueue(fake_redis, "10001", user_text="hi")
    await takeover_svc.record_manual_reply(fake_redis, "10001", "手动回", sent_ts=2000)
    assert called["n"] == 1


async def test_record_manual_reply_reply_ts_guard(fake_redis, monkeypatch, fake_adapter):
    """ts 顺序保护:sent_ts 早于 pending created_ts(时钟偏移)时 reply_ts 仍晚于 user_ts"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await takeover_store.enqueue(fake_redis, "10001", user_text="hi")   # created_ts=now(ms)
    await takeover_svc.record_manual_reply(fake_redis, "10001", "答", sent_ts=1)   # 异常早
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert len(msgs) == 2 and msgs[1]["ts"] > msgs[0]["ts"]   # 回复仍晚于用户消息


# ================ skip 归档 + 一键清空(2026-09-07)================

async def test_skip_and_archive(fake_redis, monkeypatch):
    """跳过归档:用户消息先落历史(sender=user,原 ts)再出队;队列清空不丢内容"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    p1 = await takeover_store.enqueue(fake_redis, "10001", user_text="弃答消息", msg_id="m1")
    r = await takeover_svc.skip_and_archive(fake_redis, "10001", None)   # 队首
    assert r["skipped"] is True and r["archived"] is True and r["pid"] == p1
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert len(msgs) == 1 and msgs[0]["sender"] == "user" and msgs[0]["content"] == "弃答消息"
    assert await takeover_store.list_queue(fake_redis, "10001") == []


async def test_skip_and_archive_miss_no_double_write(fake_redis, monkeypatch):
    """skip 落空(并发已被消费)不归档,防同一消息双写"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    p1 = await takeover_store.enqueue(fake_redis, "10001", user_text="x")
    await takeover_store.skip(fake_redis, "10001", p1)   # 模拟并发先消费
    r = await takeover_svc.skip_and_archive(fake_redis, "10001", p1)
    assert r["skipped"] is False
    assert await chat_store.list_messages(fake_redis, "10001") == []


async def test_clear_queue_archives_each(fake_redis, monkeypatch):
    """一键清空:逐条归档(各自独立消息,与手动回复的合并语义不同)后清队"""
    import asyncio
    monkeypatch.setattr(settings, "memory_enabled", False)
    await takeover_store.enqueue(fake_redis, "10001", user_text="a")
    await asyncio.sleep(0.002)   # 隔 2ms:防同毫秒 ts ZSet 平局排序不稳定(老坑)
    await takeover_store.enqueue(fake_redis, "10001", user_text="b")
    r = await takeover_svc.clear_queue(fake_redis, "10001")
    assert r == {"cleared": 2, "archived": 2, "failed": 0}
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert [m["content"] for m in msgs] == ["a", "b"]
    assert all(m["sender"] == "user" for m in msgs)
    assert await takeover_store.list_queue(fake_redis, "10001") == []


# ================ 审查修复回归(2026-09-07)================

async def test_record_manual_reply_chain_fail_fallback_archive(fake_redis, monkeypatch, fake_adapter):
    """审查修复:副作用链失败(run_post_reply_chain 抛)→ 降级直接归档,消息不丢"""
    monkeypatch.setattr(settings, "memory_enabled", False)

    async def boom_chain(*a, **k):
        raise RuntimeError("chain boom")
    monkeypatch.setattr("pipeline.stages.run_post_reply_chain", boom_chain)
    await takeover_store.enqueue(fake_redis, "10001", user_text="hi")
    r = await takeover_svc.record_manual_reply(fake_redis, "10001", "答", sent_ts=2000)
    assert r["archived_pendings"] == 1                        # 仍算消化
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert [m["sender"] for m in msgs] == ["user", "proxy"]   # 降级归档两条都在
    assert msgs[1]["source"] == "manual"


async def test_record_manual_reply_total_fail_requeues(fake_redis, monkeypatch, fake_adapter):
    """审查修复:副作用链+降级归档都失败 → requeue 回灌待答队列,消息不丢"""
    monkeypatch.setattr(settings, "memory_enabled", False)

    async def boom_chain(*a, **k):
        raise RuntimeError("chain boom")
    monkeypatch.setattr("pipeline.stages.run_post_reply_chain", boom_chain)

    async def boom_append(*a, **k):
        raise RuntimeError("append boom")
    monkeypatch.setattr("storage.chat_store.append_message", boom_append)
    await takeover_store.enqueue(fake_redis, "10001", user_text="hi")
    r = await takeover_svc.record_manual_reply(fake_redis, "10001", "答", sent_ts=2000)
    assert r == {"proxy_mid": "", "archived_pendings": 0, "scored": False}
    q = await takeover_store.list_queue(fake_redis, "10001")  # 回灌,可再代答
    assert len(q) == 1 and q[0]["user_text"] == "hi"
    assert q[0]["status"] == "pending"


async def test_skip_and_archive_archive_fail_keeps_detail(fake_redis, monkeypatch):
    """审查修复:归档 append 失败不崩,pending 详情留存(status=skipped Hash 在)"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    p1 = await takeover_store.enqueue(fake_redis, "10001", user_text="要留的")
    calls = {"n": 0}

    async def flaky_append(redis, oid, **k):
        calls["n"] += 1
        raise RuntimeError("append boom")
    monkeypatch.setattr("storage.chat_store.append_message", flaky_append)
    r = await takeover_svc.skip_and_archive(fake_redis, "10001", None)
    assert r["skipped"] is True and r["archived"] is False     # 占位成功,归档失败
    assert await takeover_store.get_pending(fake_redis, "10001", p1) is not None  # 详情留存


async def test_clear_queue_partial_fail_counts(fake_redis, monkeypatch):
    """审查修复:逐条容错——第 2 条归档失败,第 1/3 条照常,failed=1"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    for t in ("a", "b", "c"):
        await takeover_store.enqueue(fake_redis, "10001", user_text=t)
    real_append = chat_store.append_message
    calls = {"n": 0}

    async def flaky_append(redis, oid, **k):
        calls["n"] += 1
        if calls["n"] == 2:                                    # 只让第 2 条失败
            raise RuntimeError("append boom")
        return await real_append(redis, oid, **k)
    monkeypatch.setattr("storage.chat_store.append_message", flaky_append)
    r = await takeover_svc.clear_queue(fake_redis, "10001")
    assert r == {"cleared": 3, "archived": 2, "failed": 1}


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
