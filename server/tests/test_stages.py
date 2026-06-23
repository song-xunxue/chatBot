"""
管道 stages 测试
验证 persona_inject 占位/不覆盖、build_messages 拼装顺序、load_history 填充

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：覆盖 stages 核心阶段
"""
from pipeline.context import MessageContext
from pipeline import stages
from llm.base import Message
from storage import chat_store


async def test_persona_inject_default_when_empty():
    ctx = MessageContext(object_id="u")
    await stages.stage_persona_inject(ctx)
    assert ctx.system_prompt  # 非空占位 prompt


async def test_persona_inject_keeps_existing():
    ctx = MessageContext(object_id="u", system_prompt="你是猫娘")
    await stages.stage_persona_inject(ctx)
    assert ctx.system_prompt == "你是猫娘"  # 已有 system_prompt 则不覆盖


async def test_build_messages_order_system_history_user():
    ctx = MessageContext(object_id="u", user_text="你好")
    ctx.system_prompt = "SYS"
    ctx.history = [
        Message(role="user", content="历史问"),
        Message(role="assistant", content="历史答"),
    ]
    msgs = await stages.stage_build_messages(ctx)
    # 顺序：system → 历史 → 本次 user
    assert [m.role for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[0].content == "SYS"
    assert msgs[-1].content == "你好"


async def test_build_messages_without_system():
    ctx = MessageContext(object_id="u", user_text="hi")
    msgs = await stages.stage_build_messages(ctx)
    assert msgs[0].role == "user" and msgs[0].content == "hi"


async def test_load_history_fills_context(fake_redis):
    await chat_store.append_message(fake_redis, "u", "user", "早")
    ctx = MessageContext(object_id="u")
    await stages.stage_load_history(ctx, fake_redis)
    assert len(ctx.history) == 1
    assert ctx.history[0].content == "早"
