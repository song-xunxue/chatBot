"""
pipeline 全链路单测(mock LLM):run_stream 产出回复 + persona/mood 注入 + save 落库。
用 mock_provider 替换 LLM,验证管道编排而非真实模型。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 创建 pipeline 全链路单测
"""
import storage.redis_client as redis_client
from storage import chat_store
from pipeline.context import MessageContext
from pipeline.runner import run_stream
from mood import service


def _inject_redis(monkeypatch, fake):
    """把 fakeredis 注入 redis_client 单例(run_stream 内部 get_redis 用)"""
    monkeypatch.setattr(redis_client, "_redis", fake)


async def test_pipeline_produces_reply(fake_redis, mock_provider, monkeypatch):
    """全链路:run_stream 产出 mock 回复 + LLM 调用 1 次 + user/ai 落库"""
    _inject_redis(monkeypatch, fake_redis)
    await service.seed_default_kinds(fake_redis)
    monkeypatch.setattr("pipeline.stages.get_provider", lambda name: mock_provider)

    ctx = MessageContext(object_id="u1", user_text="你好")
    tokens = [t async for t in run_stream(ctx)]

    assert ctx.reply_text == "mock-reply"
    assert mock_provider.call_count == 1
    # chat_store 落了 user + ai 两条
    history = await chat_store.get_history(fake_redis, "u1")
    assert [m.role for m in history] == ["user", "assistant"]


async def test_pipeline_system_prompt_has_persona_and_mood(fake_redis, mock_provider, monkeypatch):
    """system_prompt 含人设指令 + 心情提示"""
    _inject_redis(monkeypatch, fake_redis)
    await service.seed_default_kinds(fake_redis)
    await service.set_mood(fake_redis, "u1", 0.9)   # happy
    monkeypatch.setattr("pipeline.stages.get_provider", lambda name: mock_provider)

    ctx = MessageContext(object_id="u1", user_text="嗨")
    async for _ in run_stream(ctx):
        pass

    sys_msg = next(m for m in mock_provider.last_messages if m.role == "system")
    assert "核心人设指令" in sys_msg.content or "友善" in sys_msg.content   # 默认人设
    assert "心情" in sys_msg.content   # mood 注入


async def test_pipeline_mood_updated_by_reply(fake_redis, mock_provider, monkeypatch):
    """after_llm 后按回复情感更新 mood(mock-reply 无情感词,mood 不变)"""
    _inject_redis(monkeypatch, fake_redis)
    await service.seed_default_kinds(fake_redis)
    await service.set_mood(fake_redis, "u1", 0.5)
    monkeypatch.setattr("pipeline.stages.get_provider", lambda name: mock_provider)

    ctx = MessageContext(object_id="u1", user_text="嗨")
    async for _ in run_stream(ctx):
        pass
    # mock-reply="mock-reply" 无情感词,mood 应保持 0.5
    assert await service.get_mood(fake_redis, "u1") == 0.5


async def test_pipeline_appends_to_block(fake_redis, mock_provider, monkeypatch):
    """多轮对话落同一 block(静默未超)"""
    _inject_redis(monkeypatch, fake_redis)
    await service.seed_default_kinds(fake_redis)
    monkeypatch.setattr("pipeline.stages.get_provider", lambda name: mock_provider)

    for text in ["第一句", "第二句"]:
        ctx = MessageContext(object_id="u1", user_text=text)
        async for _ in run_stream(ctx):
            pass
    # 4 条消息(user+ai × 2)在同一 block
    assert await chat_store.count_messages(fake_redis, "u1") == 4
