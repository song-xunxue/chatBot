"""
stage_score / pipeline 评分接入单测:run_stream 全链路后 ai 回复被自动评分
(reply_mid 填充 + score 四元组写入)、score_enabled=False 降级、评分 LLM 异常不阻塞主流程。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 创建 stage_score 单测(评分接入/开关降级/异常不阻塞)
"""
import storage.redis_client as redis_client
from pipeline.context import MessageContext
from pipeline.runner import run_stream
from mood import service as mood_service
from score import service as score_service
from core.config import settings


def _inject_redis(monkeypatch, fake):
    """把 fakeredis 注入 redis_client 单例(run_stream 内 get_redis 用)"""
    monkeypatch.setattr(redis_client, "_redis", fake)


async def test_stage_score_scores_ai_reply(fake_redis, make_provider, monkeypatch):
    """run_stream 后:ctx.reply_mid 填充 + ai 消息被自动评分(base 写入)"""
    _inject_redis(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    # 对话 LLM(stream)与评分 LLM 分别 mock(走不同模块的 get_provider)
    monkeypatch.setattr("pipeline.stages.get_provider", lambda n: make_provider("mock-reply"))
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    monkeypatch.setattr("score.service.get_provider",
                        lambda n: make_provider('{"score": 88, "reason": "契合"}'))

    ctx = MessageContext(object_id="u1", user_text="你好")
    async for _ in run_stream(ctx):
        pass
    assert ctx.reply_mid                                # stage_save 填了 ai mid
    got = await score_service.get_score(fake_redis, ctx.reply_mid)
    assert got["score_base"] == 88
    assert 85 <= int(got["score"]) <= 91                # calm(0.5) bias 0±3


async def test_stage_score_disabled_skips(fake_redis, make_provider, monkeypatch):
    """score_enabled=False:跳过评分,ai 消息无分"""
    _inject_redis(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    monkeypatch.setattr(settings, "score_enabled", False)
    monkeypatch.setattr("pipeline.stages.get_provider", lambda n: make_provider("mock-reply"))
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    monkeypatch.setattr("score.service.get_provider", lambda n: make_provider('{"score": 88}'))

    ctx = MessageContext(object_id="u1", user_text="你好")
    async for _ in run_stream(ctx):
        pass
    got = await score_service.get_score(fake_redis, ctx.reply_mid)
    assert got["score"] is None                         # 评分关,未打分


async def test_stage_score_llm_garbage_no_block(fake_redis, make_provider, monkeypatch):
    """评分 LLM 返回垃圾:score_reply 返回 None,但主流程不抛,回复与历史正常落库"""
    _inject_redis(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    monkeypatch.setattr("pipeline.stages.get_provider", lambda n: make_provider("mock-reply"))
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    monkeypatch.setattr("score.service.get_provider", lambda n: make_provider("解析不了"))

    ctx = MessageContext(object_id="u1", user_text="你好")
    async for _ in run_stream(ctx):
        pass
    assert ctx.reply_text == "mock-reply"               # 主回复不受影响
    got = await score_service.get_score(fake_redis, ctx.reply_mid)
    assert got["score"] is None                         # 评分失败降级,无分
