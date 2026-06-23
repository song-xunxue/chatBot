"""
MemoryCoordinator 检索 + 组装测试
验证关键词召回 top-K、访问统计更新、Core 全量注入、Episodic 近摘要、
render 顺序（长期在前摘要在后）、空降级、forgotten 排除、无匹配返回空

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.3 覆盖 coordinator.retrieve/render
"""
import pytest

from memory.coordinator import MemoryCoordinator
from memory import store
from memory.models import MemoryItem, EpisodicEntry, CoreFact


@pytest.fixture
def coord(fake_redis):
    """直接构造协调器（绑定当前测试的 fakeredis），不走单例"""
    return MemoryCoordinator(fake_redis)


async def test_retrieve_long_term_keyword_match(coord, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="用户喜欢猫"))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m2", content="今天天气晴朗"))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m3", content="猫很可爱"))
    result = await coord.retrieve("u", query="猫", top_k=5)
    mids = {m.id for m in result.long_term}
    assert "m1" in mids and "m3" in mids   # 含"猫"
    assert "m2" not in mids                 # 不含


async def test_retrieve_topk_limit(coord, fake_redis):
    for i in range(5):
        await store.upsert_long_term(fake_redis, "u", MemoryItem(id=f"m{i}", content=f"猫咪{i}"))
    result = await coord.retrieve("u", query="猫", top_k=2)
    assert len(result.long_term) == 2


async def test_retrieve_updates_access_stats(coord, fake_redis):
    await store.upsert_long_term(fake_redis, "u",
                                 MemoryItem(id="m1", content="猫", access_count=0))
    await coord.retrieve("u", query="猫", top_k=5)
    m = await store.get_long_term(fake_redis, "u", "m1")
    assert m.access_count == 1            # 召回即访问（间隔重复）


async def test_retrieve_core_always_returned(coord, fake_redis):
    await store.set_core(fake_redis, "u", [CoreFact(key="name", content="小明")])
    result = await coord.retrieve("u", query="任何无关词")
    assert len(result.core) == 1
    assert result.core[0].content == "小明"


async def test_retrieve_episodic_recent(coord, fake_redis):
    for i in range(5):
        await store.append_episodic(fake_redis, "u", EpisodicEntry(
            id=f"e{i}", summary=f"摘要{i}", span_start_ts=i, span_end_ts=i, created_ts=1000 + i))
    result = await coord.retrieve("u", query="x")
    assert len(result.episodic) == 3      # limit=3


async def test_render_order_long_then_episodic(coord, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="事实A"))
    await store.append_episodic(fake_redis, "u", EpisodicEntry(
        id="e1", summary="摘要B", span_start_ts=0, span_end_ts=0))
    result = await coord.retrieve("u", query="事实")
    block = coord.render(result)
    assert "【相关长期记忆】" in block and "事实A" in block
    assert "【近期对话摘要】" in block and "摘要B" in block
    assert block.index("相关长期记忆") < block.index("近期对话摘要")


async def test_render_empty_when_no_memory(coord, fake_redis):
    result = await coord.retrieve("u", query="x")
    assert coord.render(result) == ""


async def test_retrieve_excludes_forgotten(coord, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="猫", forgotten=True))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m2", content="猫2"))
    result = await coord.retrieve("u", query="猫")
    assert {m.id for m in result.long_term} == {"m2"}


async def test_retrieve_no_match_returns_empty_long(coord, fake_redis):
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="完全无关的内容"))
    result = await coord.retrieve("u", query="猫")
    assert result.long_term == []


async def test_retrieve_working_passed_through(coord, fake_redis):
    result = await coord.retrieve("u", query="x", working_messages=["msg1", "msg2"])
    assert result.working == ["msg1", "msg2"]


async def test_retrieve_english_token_case_insensitive(coord, fake_redis):
    """英文 token 召回 + 大小写归一化（_tokenize 已 lower）"""
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m1", content="用户在写 Python 代码"))
    await store.upsert_long_term(fake_redis, "u", MemoryItem(id="m2", content="今天天气晴朗"))
    result = await coord.retrieve("u", query="PYTHON", top_k=5)
    mids = {m.id for m in result.long_term}
    assert "m1" in mids   # 含英文 token 'python'，经 lower() 归一后命中
    assert "m2" not in mids
