"""
score.record_negative_sample + 软删联动单测(M7)。
record_negative_sample 是软删联动公开封装(供 rest_chat DELETE ai/proxy 消息时扩充反推负样本)。
本测试验证数据流;实际 DELETE 端点联动在 test_rest_chat(M7b)测。

作者: 李文煜
日期: 2026-06-30
"""
from score import service as score_service
from storage import chat_store


async def test_record_negative_sample_writes_neg(fake_redis):
    """record_negative_sample 写 neg 队列,结构与 _collect_sample 一致({mid,text,score,ts})"""
    await score_service.record_negative_sample(fake_redis, "u1", "mid1", "差回复", 30)
    neg = await score_service.list_samples(fake_redis, "u1", "negative")
    assert len(neg) == 1
    assert neg[0]["mid"] == "mid1"
    assert neg[0]["text"] == "差回复"
    assert neg[0]["score"] == 30
    assert "ts" in neg[0]


async def test_record_negative_not_pollute_positive(fake_redis):
    """写 neg 不污染 pos 队列"""
    await score_service.record_negative_sample(fake_redis, "u1", "mid1", "差", 30)
    assert await score_service.list_samples(fake_redis, "u1", "positive") == []


async def test_softdelete_linkage_flow(fake_redis):
    """模拟 rest_chat 软删联动全流程:删 ai 消息(有 score)→ record_negative_sample → neg 多一条。
    验证联动数据流逻辑(实际 REST 端点封装在 M7b rest_chat)。"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="跑偏回复")
    await chat_store.set_score(fake_redis, mid, score_base=30, mood_value=0.5, mood_bias=0)
    msg = await chat_store.get_message(fake_redis, mid)
    # 联动判定:sender∈(ai,proxy) 且 score 非空 → 软删 + 写 neg
    assert msg["sender"] in ("ai", "proxy")
    assert msg.get("score", "") != ""
    await chat_store.delete_message(fake_redis, mid, reason="out_of_character")
    await score_service.record_negative_sample(
        fake_redis, msg["object_id"], mid, msg["content"], int(float(msg["score"])))
    neg = await score_service.list_samples(fake_redis, "u1", "negative")
    assert len(neg) == 1
    assert neg[0]["mid"] == mid


async def test_softdelete_user_message_no_linkage(fake_redis):
    """user 消息软删不联动(user 非 ai/proxy,不写 neg)"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="user", content="用户说的")
    await chat_store.delete_message(fake_redis, mid)
    # user 消息无 score 且 sender 不符联动条件 → neg 仍空
    assert await score_service.list_samples(fake_redis, "u1", "negative") == []
