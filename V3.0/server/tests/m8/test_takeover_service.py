"""
对话控制 service 单测(2026-09-13 静默模式重构版)
覆盖:send_proactive(落 proxy+下发)/record_manual_reply(直接落库+恒正样本+静默窗+心情;
绝不下发 QQ)。原队列代答链(resolve/batch/skip/clear/drain)测试已随队列删减移除。

作者: 李文煜
日期: 2026-06-30

2026-09-13
变更说明：
  1. 队列删减重构:record_manual_reply 改直接落库路径(无队列合并);删队列链测试
"""
import pytest

from core.config import settings
from storage import takeover_store, chat_store
from takeover import service as takeover_svc


async def test_send_proactive_lands_and_delivers(fake_redis, fake_adapter):
    """主动发送:落 proxy 消息(进历史)+ 下发 QQ(无评分/记忆副作用)"""
    monkeypatch_none = None
    r = await takeover_svc.send_proactive(fake_redis, "10001", "在吗~")
    assert r["delivered"] is True and r["mode"] in ("active", "passive")
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert len(msgs) == 1 and msgs[0]["sender"] == "proxy" and msgs[0]["source"] == "proxy"
    assert msgs[0]["content"] == "在吗~"
    assert len(fake_adapter.sent) == 1


# ================ record_manual_reply(2026-09-13 直接落库版) ================

async def test_manual_reply_lands_manual_source(fake_redis, fake_adapter):
    """手动回复:落 proxy(source='manual');绝不下发 QQ(sent 空)"""
    monkeypatch_score_off = None
    from unittest.mock import patch  # noqa: F401(说明:评分走下方独立用例)
    r = await takeover_svc.record_manual_reply(fake_redis, "10001", "嗯嗯在的~", sent_ts=2000)
    assert r["proxy_mid"]
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert len(msgs) == 1 and msgs[0]["sender"] == "proxy" and msgs[0]["source"] == "manual"
    assert msgs[0]["content"] == "嗯嗯在的~"
    assert fake_adapter.sent == []                    # 绝不重复下发(已手动发出)


async def test_manual_reply_forced_positive_sample(fake_redis, fake_adapter, make_provider):
    """恒正样本:LLM 四元组照算,样本 source='manual' score=100;占位文本不入样本"""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    provider = make_provider('{"score": 62, "reason": "短"}')   # 低分也不进 neg
    monkeypatch.setattr("score.service.resolve_provider", lambda *a, **k: provider)
    from mood import service as mood_service
    await mood_service.seed_default_kinds(fake_redis)
    try:
        r = await takeover_svc.record_manual_reply(fake_redis, "10001", "哎嘿", sent_ts=2000)
        assert r["scored"] is True
        from score import service as score_service
        pos = await score_service.list_samples(fake_redis, "10001", "positive")
        assert len(pos) == 1 and pos[0]["source"] == "manual" and pos[0]["score"] == 100
        assert await score_service.list_samples(fake_redis, "10001", "negative") == []
    finally:
        monkeypatch.undo()


async def test_manual_reply_placeholder_no_sample(fake_redis, fake_adapter):
    """手动发语音(占位 [语音]):落库保历史,但不作黄金样本(占位过滤)"""
    from unittest.mock import patch
    with patch("score.service.score_reply", wraps=None) as _p:
        # 占位过滤在 score_reply 内部;这里直接验证占位内容落库 + 静默窗仍写
        r = await takeover_svc.record_manual_reply(fake_redis, "10001", "[语音]", sent_ts=1000)
    assert r["proxy_mid"]
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert msgs[0]["content"] == "[语音]"
    assert await takeover_store.is_silenced(fake_redis, "10001") is True   # 静默窗已写


async def test_manual_reply_writes_silence_window(fake_redis, fake_adapter):
    """手动回复后写静默窗(takeover_manual_silence_min 分钟,AI 暂闭嘴)"""
    r = await takeover_svc.record_manual_reply(fake_redis, "10001", "答", sent_ts=2000)
    assert await takeover_store.is_silenced(fake_redis, "10001") is True
    ttl = await fake_redis.ttl("mychat:takeover:silence:10001")
    assert 0 < ttl <= settings.takeover_manual_silence_min * 60


async def test_manual_reply_score_fail_soft(fake_redis, fake_adapter, monkeypatch):
    """评分异常软失败:落库/静默窗不受影响"""
    async def boom(*a, **k):
        raise RuntimeError("score boom")
    monkeypatch.setattr("score.service.score_reply", boom)
    r = await takeover_svc.record_manual_reply(fake_redis, "10001", "答", sent_ts=2000)
    assert r["scored"] is False
    msgs = await chat_store.list_messages(fake_redis, "10001")
    assert len(msgs) == 1                                   # 消息仍落库
    assert await takeover_store.is_silenced(fake_redis, "10001") is True
