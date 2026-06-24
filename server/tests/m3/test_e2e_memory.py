"""
M3.6 端到端集成测试
验证 pipeline 全链路：人设注入 + 记忆检索注入 + LLM 流式 + 历史保存 + 记忆编码，
以及第二轮对话把上一轮编码的记忆召回注入。
用 mock provider（避免真实 GLM 调用）+ fakeredis。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.6 端到端覆盖：人设+记忆注入、流式累积、历史保存、事实编码、跨轮召回
"""
import asyncio

import pytest

from pipeline.context import MessageContext
from pipeline import runner, stages
from llm.base import Delta, LLMResponse
from memory import store
from memory.models import MemoryItem
from persona import store as persona_store
from persona.models import PersonaCard


class _FakeProvider:
    """假 LLM：stream_chat 产固定 token；chat 返回固定事实 JSON（供 extract_facts）"""
    name = "fake"

    def __init__(self):
        self.received = None

    async def stream_chat(self, messages, model="", **opts):
        self.received = messages
        for t in ["好", "的"]:
            yield Delta(text=t)

    async def chat(self, messages, model="", **opts):
        return LLMResponse(
            text='[{"content":"用户喜欢猫","importance":0.8,"emotion":0.5,"category":"preference"}]')


@pytest.fixture
def fake_provider(monkeypatch):
    fp = _FakeProvider()
    monkeypatch.setattr(stages, "get_provider", lambda name: fp)
    return fp


@pytest.fixture
def fake_coord(monkeypatch, fake_redis, fake_provider):
    """协调器绑定 fakeredis + fake LLM，并 patch get_memory_coordinator 返回它
    （避免真实 GLM 调用）"""
    from memory.coordinator import MemoryCoordinator
    import memory.coordinator as mc
    coord = MemoryCoordinator(fake_redis, llm_provider=fake_provider)

    async def _get():
        return coord

    monkeypatch.setattr(mc, "get_memory_coordinator", _get)
    return coord


async def test_e2e_persona_and_memory_injected(fake_coord, fake_redis, fake_provider):
    """一轮对话：人设 + 召回记忆 拼进 system_prompt，流式累积，历史保存。
    并断言 memory_retrieve 在 llm_stream 之前完成（LLM 收到的 system message 必含 memory_block）"""
    await persona_store.set_persona(fake_redis,
        PersonaCard(id="default", name="小聊", creator_notes="你是贴心助手"))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="用户喜欢猫"))

    ctx = MessageContext(object_id="u", user_text="猫", provider_name="glm", created_ts=1000)
    tokens = [t async for t in runner.run_stream(ctx)]

    assert tokens == ["好", "的"]
    assert ctx.reply_text == "好的"
    assert "助手" in ctx.system_prompt          # 人设注入
    assert "猫" in ctx.memory_block             # 记忆召回
    hist = await store.get_working_span(fake_redis, "u", 1)
    assert len(hist) == 2                        # 历史（user+assistant）保存
    # stage 顺序硬约束：memory_retrieve 先于 llm_stream，故 LLM 收到的 system message 已含 memory_block
    received = fake_provider.received
    assert received is not None and received[0].role == "system"
    assert "猫" in received[0].content


async def test_e2e_memory_encoded_after_turn(fake_coord, fake_redis):
    """一轮对话后，事实抽取写入长期记忆"""
    await persona_store.get_default_persona(fake_redis)
    ctx = MessageContext(object_id="u2", user_text="我超喜欢猫",
                         provider_name="glm", created_ts=2000)
    async for _ in runner.run_stream(ctx):
        pass
    await asyncio.sleep(0.2)  # 等 stage_memory_write 的 create_task 完成
    items = await store.get_all_long_term(fake_redis, "u2")
    assert any("猫" in m.content for m in items)


async def test_e2e_memory_recalled_next_turn(fake_coord, fake_redis):
    """第二轮：第一轮编码的记忆被召回注入 memory_block"""
    await persona_store.get_default_persona(fake_redis)
    ctx1 = MessageContext(object_id="u3", user_text="我喜欢猫",
                          provider_name="glm", created_ts=3000)
    async for _ in runner.run_stream(ctx1):
        pass
    await asyncio.sleep(0.2)

    ctx2 = MessageContext(object_id="u3", user_text="再说猫",
                          provider_name="glm", created_ts=4000)
    async for _ in runner.run_stream(ctx2):
        pass
    assert "猫" in ctx2.memory_block  # 上一轮写入的记忆被召回


async def test_e2e_memory_disabled_degrades(fake_coord, fake_redis, monkeypatch):
    """memory_enabled=False 时降级：不检索、不注入、仍正常回复"""
    from core.config import settings
    monkeypatch.setattr(settings, "memory_enabled", False)
    await persona_store.get_default_persona(fake_redis)
    ctx = MessageContext(object_id="u4", user_text="你好", provider_name="glm", created_ts=5000)
    tokens = [t async for t in runner.run_stream(ctx)]
    assert tokens == ["好", "的"]
    assert ctx.memory_block == ""  # 降级不注入
