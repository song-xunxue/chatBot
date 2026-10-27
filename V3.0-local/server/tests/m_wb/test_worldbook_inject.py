"""
世界书注入接线单测(docs/09 验收#1/#2/#3):
legacy 回归锁定(MEMORY_MODE=legacy 时 stage_build_messages 输出与旧拼接公式逐字一致)/
worldbook 分支(stage_memory_retrieve 分流、锚点拼装顺序、概率与冷却、记账、向量兜底 topup)。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新增:legacy 逐字回归 + worldbook 注入全路径单测
"""
import pytest

from core.config import settings
from llm.base import Message
from memory import worldbook_store
from memory.worldbook import WbEntry
from pipeline.context import MessageContext
from pipeline.stages import stage_build_messages, stage_memory_retrieve
from persona.renderer import OUTPUT_CONTRACT


def _e(eid="wb_x", **kw) -> WbEntry:
    d = dict(id=eid, title="标题", content="内容", keys=[], mode="trigger", enabled=True)
    d.update(kw)
    return WbEntry(**d)


def _ctx(user_text="打雷了") -> MessageContext:
    ctx = MessageContext(object_id="10001", user_text=user_text)
    ctx.history = [Message(role="user", content="在吗"),
                   Message(role="assistant", content="嗯呢")]
    return ctx


# ================ legacy 回归锁定(验收#1:逐字一致) ================

async def test_legacy_build_messages_identical(monkeypatch):
    """MEMORY_MODE=legacy(默认):build 输出与旧公式 f"{sp}\\n\\n{mb}"+CONTRACT 逐字一致。
    sections 恒空 dict,锚点代码不得改变 legacy 拼装结果"""
    monkeypatch.setattr(settings, "memory_mode", "legacy")
    # 有 system_prompt 的两种形态(记忆块有/无)
    for sp, mb in [("人设A", "记忆B"), ("人设A", "")]:
        ctx = MessageContext(object_id="10001", user_text="hi")
        ctx.system_prompt = sp
        ctx.memory_block = mb
        msgs = await stage_build_messages(ctx)
        expect = (f"{sp}\n\n{mb}" if mb else sp) + OUTPUT_CONTRACT
        assert msgs[0].role == "system"
        assert msgs[0].content == expect       # 逐字一致
        assert msgs[-1].content == "hi"
    # 无 system_prompt:与旧逻辑一致不产 system 消息(memory_block 也不再有挂点)
    ctx = MessageContext(object_id="10001", user_text="hi")
    ctx.memory_block = "记忆B"
    msgs = await stage_build_messages(ctx)
    assert all(m.role != "system" for m in msgs)


async def test_legacy_retrieve_untouched(monkeypatch, fake_redis):
    """legacy 模式 stage_memory_retrieve 走原 coordinator 路径:产出 memory_block
    (legacy 渲染格式),worldbook_sections 恒不被填充"""
    monkeypatch.setattr(settings, "memory_mode", "legacy")
    await worldbook_store.upsert_entry(fake_redis, _e("wb_a", mode="always", content="常驻设定"))
    await (await _coord(fake_redis)).upsert_fact(
        "10001", {"content": "他喜欢猫", "category": "preference"})
    ctx = _ctx("他喜欢猫吗")
    await stage_memory_retrieve(ctx, fake_redis)
    assert ctx.worldbook_sections == {}            # 世界书条目不进 legacy 注入
    assert "他喜欢猫" in ctx.memory_block          # legacy 检索渲染照旧(BM25 命中)
    assert "worldbook_injected" not in ctx.memory_meta


async def _coord(fake_redis):
    """独立 coordinator(直连 fake redis,无 LLM)"""
    from memory.coordinator import MemoryCoordinator
    return MemoryCoordinator(fake_redis, llm_provider=None)


# ================ worldbook 分支 ================

async def test_worldbook_mode_inject_anchors(monkeypatch, fake_redis):
    """worldbook 模式:命中条目按 position 锚点进 sections;memory_block 停用;
    build 按锚点序拼进 system prompt"""
    monkeypatch.setattr(settings, "memory_mode", "worldbook")
    await worldbook_store.upsert_entry(
        fake_redis, _e("wb_p", mode="always", content="她叫角色A", position="after_persona"))
    await worldbook_store.upsert_entry(
        fake_redis, _e("wb_m", keys=["打雷"], content="打雷时她会缩起来",
                       position="before_memories"))
    await worldbook_store.upsert_entry(
        fake_redis, _e("wb_t", keys=["打雷"], content="夜间情绪偏脆弱", position="tail"))
    ctx = _ctx()
    ctx.system_prompt = "【核心人设指令】\n她是角色A"
    await stage_memory_retrieve(ctx, fake_redis)
    assert ctx.worldbook_sections == {
        "after_persona": "- 她叫角色A",
        "before_memories": "- 打雷时她会缩起来",
        "tail": "- 夜间情绪偏脆弱",
    }
    assert ctx.memory_block == ""                   # legacy 全量注入停用
    msgs = await stage_build_messages(ctx)
    sysc = msgs[0].content
    # 锚点顺序:persona 内(before 无) → after_persona → before_memories → tail,契约最后
    assert sysc.index("她是角色A") < sysc.index("- 她叫角色A") < \
        sysc.index("- 打雷时她会缩起来") < sysc.index("- 夜间情绪偏脆弱") < \
        sysc.index(OUTPUT_CONTRACT[:20])
    assert ctx.memory_meta["worldbook_injected"] == ["wb_p", "wb_m", "wb_t"]
    assert ctx.memory_meta["worldbook_tokens"] > 0


async def test_worldbook_miss_no_inject(monkeypatch, fake_redis):
    """未命中 trigger 条目不注入;always 仍注入;hit_ids 只含候选"""
    monkeypatch.setattr(settings, "memory_mode", "worldbook")
    await worldbook_store.upsert_entry(fake_redis,
                                       _e("wb_m", keys=["下雨"], content="下雨相关"))
    await worldbook_store.upsert_entry(fake_redis,
                                       _e("wb_p", mode="always", content="常驻", position="tail"))
    ctx = _ctx("今天好热")
    await stage_memory_retrieve(ctx, fake_redis)
    assert ctx.worldbook_sections == {"tail": "- 常驻"}
    assert ctx.memory_meta["worldbook_injected"] == ["wb_p"]


async def test_worldbook_cooldown_and_probability(monkeypatch, fake_redis):
    """冷却未过与 probability=0 的条目不注入;命中未注入只刷 last_hit_at"""
    import time
    monkeypatch.setattr(settings, "memory_mode", "worldbook")
    now = int(time.time() * 1000)
    hot = _e("wb_hot", keys=["打雷"], content="刚注入过", cooldown_minutes=30,
             last_injected_at=now - 60_000)
    p0 = _e("wb_p0", keys=["打雷"], content="零概率", probability=0.0)
    await worldbook_store.upsert_entry(fake_redis, hot)
    await worldbook_store.upsert_entry(fake_redis, p0)
    ctx = _ctx()
    await stage_memory_retrieve(ctx, fake_redis)
    assert ctx.worldbook_sections == {}
    assert ctx.memory_meta["worldbook_injected"] == []
    e1 = await worldbook_store.get_entry(fake_redis, "wb_hot")
    e2 = await worldbook_store.get_entry(fake_redis, "wb_p0")
    assert e1.hits == 0 and e1.last_hit_at >= now - 60_000   # 命中记账但 hits 不增
    assert e2.hits == 0


async def test_worldbook_injection_stats_recorded(monkeypatch, fake_redis):
    """注入后 hits/last_injected_at 与全局 stats 均记账"""
    monkeypatch.setattr(settings, "memory_mode", "worldbook")
    await worldbook_store.upsert_entry(fake_redis,
                                       _e("wb_a", mode="always", content="常驻", position="tail"))
    ctx = _ctx()
    await stage_memory_retrieve(ctx, fake_redis)
    e = await worldbook_store.get_entry(fake_redis, "wb_a")
    assert e.hits == 1 and e.last_injected_at > 0
    s = await worldbook_store.get_stats(fake_redis)
    assert s["today_injections"] == 1 and s["avg_tokens"] > 0


async def test_worldbook_topup_from_retriever(monkeypatch, fake_redis):
    """候选中 memory 来源不足 → 向量兜底召回补(recall_topup 条,临时条目进渲染
    不落库;hit_mids 回填 memory_meta 维持评分回流)"""
    monkeypatch.setattr(settings, "memory_mode", "worldbook")
    monkeypatch.setattr(settings, "worldbook_recall_topup", 2)
    # 只放 manual 条目(无 memory 来源)触发兜底;种记忆给 retriever 召回
    await worldbook_store.upsert_entry(fake_redis,
                                       _e("wb_man", source="manual", mode="always",
                                          content="手写设定", position="tail"))
    from memory.models import MemoryItem
    from memory import store as mem_store
    for i in range(3):
        await mem_store.upsert_long_term(fake_redis, "10001", MemoryItem(
            id=f"mem_{i}", content=f"他喜欢猫粮品牌{i}号", category="preference"))
    ctx = _ctx(user_text="他喜欢什么猫粮")
    await stage_memory_retrieve(ctx, fake_redis)
    # 兜底临时条目进了渲染(topup_ 前缀不出现在落库条目里)
    joined = "\n".join(ctx.worldbook_sections.values())
    assert "猫粮" in joined
    assert all(not i.startswith("topup_") for i in ctx.memory_meta["worldbook_injected"])
    assert ctx.memory_meta.get("hit_mids")              # 评分回流口径对齐
    # 临时条目不落库:worldbook 条目仍只有 1 条 manual
    items = await worldbook_store.list_entries(fake_redis)
    assert len(items) == 1 and items[0].source == "manual"


async def test_worldbook_inject_failure_soft(monkeypatch, fake_redis):
    """注入过程异常(如存储炸)→ 软降级空 sections,不抛出不阻塞回复"""
    monkeypatch.setattr(settings, "memory_mode", "worldbook")

    async def _boom(*a, **kw):
        raise RuntimeError("redis down")

    monkeypatch.setattr(worldbook_store, "list_entries", _boom)
    ctx = _ctx()
    await stage_memory_retrieve(ctx, fake_redis)   # 不应抛
    assert ctx.worldbook_sections == {}
