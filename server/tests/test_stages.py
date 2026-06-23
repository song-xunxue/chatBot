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
from memory import store


async def test_persona_inject_default_when_empty(fake_redis):
    from persona import store
    await store.get_default_persona(fake_redis)  # seed 默认人设
    ctx = MessageContext(object_id="u")
    await stages.stage_persona_inject(ctx, fake_redis)
    assert ctx.system_prompt  # 默认人设渲染非空
    assert ctx.persona_id == "default"


async def test_persona_inject_keeps_existing_system_prompt(fake_redis):
    from persona import store
    await store.get_default_persona(fake_redis)
    ctx = MessageContext(object_id="u", system_prompt="你是猫娘")
    await stages.stage_persona_inject(ctx, fake_redis)
    assert ctx.system_prompt == "你是猫娘"  # 已有 system_prompt 则不覆盖


async def test_persona_inject_loads_bound_persona(fake_redis):
    from persona import store
    from persona.models import PersonaCard
    # 绑定自定义人设
    await store.set_persona(fake_redis, PersonaCard(id="cat", name="猫娘", creator_notes="你是猫娘"))
    await store.bind_object_persona(fake_redis, "u_cat", "cat")
    ctx = MessageContext(object_id="u_cat")
    await stages.stage_persona_inject(ctx, fake_redis)
    assert ctx.persona_id == "cat"
    assert "猫娘" in ctx.system_prompt


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


async def test_build_messages_appends_memory_block():
    ctx = MessageContext(object_id="u", user_text="hi", system_prompt="SYS")
    ctx.memory_block = "【相关长期记忆】\n- 事实X"
    msgs = await stages.stage_build_messages(ctx)
    assert msgs[0].role == "system"
    assert "SYS" in msgs[0].content and "事实X" in msgs[0].content  # memory_block 拼进 system 尾部


async def test_build_messages_no_memory_block_unchanged():
    ctx = MessageContext(object_id="u", user_text="hi", system_prompt="SYS")
    msgs = await stages.stage_build_messages(ctx)
    assert msgs[0].content == "SYS"


async def test_stage_memory_retrieve_disabled(monkeypatch, fake_redis):
    from core.config import settings
    monkeypatch.setattr(settings, "memory_enabled", False)
    ctx = MessageContext(object_id="u", user_text="hi")
    await stages.stage_memory_retrieve(ctx, fake_redis)
    assert ctx.memory_block == ""  # 降级：不检索


async def test_stage_memory_retrieve_fills_block(fake_redis):
    from memory.models import MemoryItem
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="用户喜欢猫"))
    ctx = MessageContext(object_id="u", user_text="猫")
    await stages.stage_memory_retrieve(ctx, fake_redis)
    assert "猫" in ctx.memory_block
    assert ctx.recall_result is not None
    assert ctx.memory_meta.get("hit_mids") == ["m1"]
