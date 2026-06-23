"""
M3.4 编码管线端到端测试
验证 coordinator.on_turn_complete：阈值触发 Episodic 摘要、事实抽取带 importance/emotion、
去重合并、失败不崩溃、无 LLM 跳过事实抽取

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.4 覆盖 on_turn_complete 编码全链路
"""
from unittest.mock import AsyncMock

from memory import store
from memory.models import MemoryItem, EpisodicEntry, Category
from llm.base import LLMResponse
from storage import chat_store
from pipeline.context import MessageContext


async def test_on_turn_summary_at_threshold(coord, fake_redis):
    # 预设 12 轮对话（24 条）→ turn_count=12 触发摘要
    for i in range(12):
        await chat_store.append_message(fake_redis, "u", "user", f"问题{i}")
        await chat_store.append_message(fake_redis, "u", "assistant", f"回答{i}")
    coord.llm = AsyncMock()
    coord.llm.chat.return_value = LLMResponse(text="用户连续问了12个问题")
    ctx = MessageContext(object_id="u", user_text="问题11", reply_text="回答11", created_ts=999)
    await coord.on_turn_complete(ctx)
    episodic = await store.get_episodic(fake_redis, "u", limit=5)
    assert len(episodic) == 1
    assert "12" in episodic[0].summary


async def test_on_turn_extracts_facts(coord, fake_redis):
    coord.llm = AsyncMock()
    coord.llm.chat.return_value = LLMResponse(
        text='[{"content":"用户喜欢猫","importance":0.8,"emotion":0.6,"category":"preference"}]')
    ctx = MessageContext(object_id="u", user_text="我超喜欢猫", reply_text="猫很可爱")
    await coord.on_turn_complete(ctx)
    items = await store.get_all_long_term(fake_redis, "u")
    cats = [m for m in items if "猫" in m.content]
    assert len(cats) == 1
    assert cats[0].importance == 0.8
    assert cats[0].emotion == 0.6
    assert cats[0].source == "dialog"               # _upsert_fact_dedup 新增分支字段
    assert cats[0].category == Category.PREFERENCE
    assert cats[0].id.startswith("mem_")


async def test_dedup_merge_similar(coord, fake_redis):
    await store.upsert_long_term(fake_redis, "u",
        MemoryItem(id="m1", content="用户喜欢猫", importance=0.5, access_count=0))
    coord.llm = AsyncMock()
    coord.llm.chat.return_value = LLMResponse(
        text='[{"content":"用户很喜欢猫咪","importance":0.9,"emotion":0.5,"category":"preference"}]')
    ctx = MessageContext(object_id="u", user_text="x", reply_text="y")
    await coord.on_turn_complete(ctx)
    items = await store.get_all_long_term(fake_redis, "u")
    assert len(items) == 1           # 合并而非新增
    assert items[0].access_count == 1
    assert items[0].importance == 0.9  # 取更高


async def test_on_turn_failure_does_not_crash(coord, fake_redis):
    coord.llm = AsyncMock()
    coord.llm.chat.side_effect = RuntimeError("LLM 挂了")
    ctx = MessageContext(object_id="u", user_text="x", reply_text="y")
    await coord.on_turn_complete(ctx)  # 不抛异常


async def test_no_llm_skips_fact_extraction(coord, fake_redis):
    coord.llm = None
    ctx = MessageContext(object_id="u", user_text="我喜欢猫", reply_text="好")
    await coord.on_turn_complete(ctx)
    assert await store.get_all_long_term(fake_redis, "u") == []  # 无 LLM 不抽取事实


async def test_on_turn_reflect_at_interval(coord, fake_redis):
    """每 reflect_interval(=5) 次摘要触发反思：预置 4 条 + 摘要 1 = 5 → 触发"""
    for i in range(4):
        await store.append_episodic(fake_redis, "u", EpisodicEntry(
            id=f"epi_{i}", summary=f"摘要{i}", span_start_ts=0, span_end_ts=i, turn_range=(0, 0)))
    for i in range(12):  # turn_count=12 → 触发摘要
        await chat_store.append_message(fake_redis, "u", "user", f"问题{i}")
        await chat_store.append_message(fake_redis, "u", "assistant", f"回答{i}")
    coord.llm = AsyncMock()
    # chat 调用顺序：摘要 → 反思 → 事实抽取
    coord.llm.chat.side_effect = [
        LLMResponse(text="本轮摘要"),
        LLMResponse(text="用户聚焦技术话题"),
        LLMResponse(text="nojson"),
    ]
    ctx = MessageContext(object_id="u", user_text="问题11", reply_text="回答11", created_ts=999)
    await coord.on_turn_complete(ctx)
    reflections = await store.get_reflections(fake_redis, "u")
    assert len(reflections) == 1
    assert reflections[0]["reflection"] == "用户聚焦技术话题"


async def test_on_turn_no_reflect_below_interval(coord, fake_redis):
    """预置 3 条 + 摘要 1 = 4，4 % 5 != 0 → 不触发反思"""
    for i in range(3):
        await store.append_episodic(fake_redis, "u", EpisodicEntry(
            id=f"epi_{i}", summary=f"摘要{i}", span_start_ts=0, span_end_ts=i, turn_range=(0, 0)))
    for i in range(12):
        await chat_store.append_message(fake_redis, "u", "user", f"问题{i}")
        await chat_store.append_message(fake_redis, "u", "assistant", f"回答{i}")
    coord.llm = AsyncMock()
    coord.llm.chat.return_value = LLMResponse(text="本轮摘要")
    ctx = MessageContext(object_id="u", user_text="问题11", reply_text="回答11", created_ts=999)
    await coord.on_turn_complete(ctx)
    assert await store.get_reflections(fake_redis, "u") == []  # 边界：4 次不触发
