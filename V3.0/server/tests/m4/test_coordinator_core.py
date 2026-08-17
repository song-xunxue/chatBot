"""
core 层激活单测(2026-07-07 记忆优化阶段3):
1. render 含【核心记忆】段(result.core 非空,常驻注入)
2. core 段排在 long_term 前(核心更靠前,权重高)
3. _upsert_core_fact 写 core + 相同 content 去重

作者: 李文煜
日期: 2026-07-07
"""
from memory.coordinator import MemoryCoordinator
from memory.models import RecallResult, CoreFact, MemoryItem


def test_render_includes_core_section():
    """优化4:render 含【核心记忆】段(core 常驻注入,非靠检索运气)"""
    c = MemoryCoordinator(redis=None)
    result = RecallResult(core=[CoreFact(key="user_name", content="用户希望被称为煜")])
    block = c.render(result)
    assert "【核心记忆】" in block
    assert "用户希望被称为煜" in block


def test_render_core_before_long_term():
    """优化4:core 段在 long_term 前(核心事实更重要,靠前权重高)"""
    c = MemoryCoordinator(redis=None)
    result = RecallResult(
        core=[CoreFact(key="k", content="核心A")],
        long_term=[MemoryItem(id="m1", content="长期B")],
    )
    block = c.render(result)
    assert block.find("核心A") < block.find("长期B")


async def test_upsert_core_fact_writes_and_dedup(fake_redis):
    """优化4:_upsert_core_fact 写 core + 相同 content 去重(归一化/Jaccard)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    await c._upsert_core_fact("u1", {"content": "用户喜欢动漫", "category": "preference"})
    await c._upsert_core_fact("u1", {"content": "用户喜欢动漫", "category": "preference"})   # 重复
    from memory import store
    core = await store.get_core(fake_redis, "u1")
    assert len(core) == 1                       # 去重,未重复堆积
    assert core[0].content == "用户喜欢动漫"
