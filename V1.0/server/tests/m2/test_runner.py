"""
管道 runner 端到端测试（fake provider + fakeredis）
验证 run_stream 的 token 流、回复累积、历史写入、多轮历史带入

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：mock LLM + 内存 Redis，跑通流式管道主干
"""
import pytest

from pipeline.context import MessageContext
from pipeline import stages, runner
from llm.base import Delta
from storage import chat_store


class _FakeProvider:
    """假 LLM：stream_chat 固定产出 token 序列，不触网"""
    name = "fake"

    def __init__(self):
        self.received_messages = None

    async def stream_chat(self, messages, model="", **opts):
        self.received_messages = messages
        for tok in ["你", "好", "呀"]:
            yield Delta(text=tok)


@pytest.fixture
def fake_provider(monkeypatch):
    fp = _FakeProvider()
    # stages 内已 from llm.registry import get_provider 绑定引用，故 patch stages 命名空间
    monkeypatch.setattr(stages, "get_provider", lambda name: fp)
    return fp


async def test_run_stream_yields_tokens_and_accumulates(fake_redis, fake_provider):
    ctx = MessageContext(object_id="u1", user_text="在吗")
    tokens = [t async for t in runner.run_stream(ctx)]
    assert tokens == ["你", "好", "呀"]
    assert ctx.reply_text == "你好呀"


async def test_run_stream_passes_user_text_to_llm(fake_redis, fake_provider):
    ctx = MessageContext(object_id="u1", user_text="今天天气")
    async for _ in runner.run_stream(ctx):
        pass
    msgs = fake_provider.received_messages
    assert msgs[-1].role == "user" and msgs[-1].content == "今天天气"
    assert msgs[0].role == "system"  # persona 占位 prompt


async def test_run_stream_saves_history(fake_redis, fake_provider):
    ctx = MessageContext(object_id="u2", user_text="嗨")
    async for _ in runner.run_stream(ctx):
        pass
    hist = await chat_store.get_history(fake_redis, "u2")
    assert len(hist) == 2
    assert hist[0].role == "user" and hist[0].content == "嗨"
    assert hist[1].role == "assistant" and hist[1].content == "你好呀"


async def test_run_stream_history_carries_to_next_turn(fake_redis, fake_provider):
    # 第一轮
    ctx1 = MessageContext(object_id="u3", user_text="第一问")
    async for _ in runner.run_stream(ctx1):
        pass
    # 第二轮：应把第一轮历史带入 messages
    ctx2 = MessageContext(object_id="u3", user_text="第二问")
    async for _ in runner.run_stream(ctx2):
        pass
    contents = [m.content for m in fake_provider.received_messages]
    assert "第一问" in contents and "你好呀" in contents and "第二问" in contents
