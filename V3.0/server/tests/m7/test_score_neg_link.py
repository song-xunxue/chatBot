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


async def test_harddelete_linkage_flow(fake_redis):
    """模拟 rest_chat 真删联动全流程(2026-08-18 软删→物理删):删 ai 消息(有 score)→
    record_negative_sample → neg 多一条,消息物理移除。验证联动数据流逻辑(REST 封装在 M7b rest_chat)。"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="跑偏回复")
    await chat_store.set_score(fake_redis, mid, score_base=30, mood_value=0.5, mood_bias=0)
    msg = await chat_store.get_message(fake_redis, mid)
    # 联动判定:sender∈(ai,proxy) 且 score 非空 → 删前写 neg + 物理删
    assert msg["sender"] in ("ai", "proxy")
    assert msg.get("score", "") != ""
    await score_service.record_negative_sample(
        fake_redis, msg["object_id"], mid, msg["content"], int(float(msg["score"])))
    assert await chat_store.hard_delete_message(fake_redis, mid) is True
    neg = await score_service.list_samples(fake_redis, "u1", "negative")
    assert len(neg) == 1
    assert neg[0]["mid"] == mid


async def test_harddelete_user_message_no_linkage(fake_redis):
    """user 消息删除不联动(user 非 ai/proxy,不写 neg;同样物理删)"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="user", content="用户说的")
    await chat_store.hard_delete_message(fake_redis, mid)
    # user 消息无 score 且 sender 不符联动条件 → neg 仍空
    assert await score_service.list_samples(fake_redis, "u1", "negative") == []
    assert await chat_store.get_message(fake_redis, mid) is None


async def test_delete_clears_pos_before_neg(fake_redis):
    """审查修复(2026-09-07):删除有 pos 样本的消息(如手动回复[手]100/纠正[纠]100)→
    先 remove_sample_by_mid 清同 mid 旧样本再写 neg——同一文本不再同时以
    黄金正样本+负样本驱动反推(互相矛盾)"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="proxy", content="手动回")
    await chat_store.set_score(fake_redis, mid, score_base=100, mood_value=0.5, mood_bias=0)
    # 该消息已有恒正样本(手动回复链路写入)
    from score.service import _collect_sample
    await _collect_sample(fake_redis, "u1", "positive", mid, "手动回", 100, source="manual")
    assert len(await score_service.list_samples(fake_redis, "u1", "positive")) == 1
    # 删除联动:remove(清 pos)→ record neg(rest_chat delete 顺序)
    await score_service.remove_sample_by_mid(fake_redis, "u1", mid)
    await score_service.record_negative_sample(fake_redis, "u1", mid, "手动回", 40)
    assert await score_service.list_samples(fake_redis, "u1", "positive") == []   # pos 已清
    neg = await score_service.list_samples(fake_redis, "u1", "negative")
    assert len(neg) == 1 and neg[0]["mid"] == mid
