"""
评分批注 score_note 单测(2026-07-07):改分带批注 → 持久化到 message + get_score 返回;
不带批注 → 字段空不报错。

作者: 李文煜
日期: 2026-07-07
"""
from storage import chat_store
from score import service as score_service


async def test_manual_set_score_with_note_persists(fake_redis):
    """改分带 score_note → 写入 message.score_note + get_score 返回"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="测试回复")
    await score_service.manual_set_score(fake_redis, mid, 85, score_note="语气自然贴合人设")
    msg = await chat_store.get_message(fake_redis, mid)
    assert msg["score_note"] == "语气自然贴合人设"
    score = await score_service.get_score(fake_redis, mid)
    assert score["score_note"] == "语气自然贴合人设"
    assert score["score_base"] == 85


async def test_manual_set_score_without_note_empty(fake_redis):
    """改分不带 score_note → 字段保持空,不报错(向后兼容)"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="测试回复")
    await score_service.manual_set_score(fake_redis, mid, 80)   # 不传 score_note
    msg = await chat_store.get_message(fake_redis, mid)
    assert msg.get("score_note", "") == ""
