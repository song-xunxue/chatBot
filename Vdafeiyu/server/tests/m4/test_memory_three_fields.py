"""
记忆三要素 + useful_score 三档衰减闭环单测(2026-08-13):
1. _parse_facts 解析 reason/tags
2. _upsert_fact_dedup 新建带 reason/tags/useful_score;去重合并 reason 取非空/tags 并集/useful_score 取 max
3. MemoryItem.from_dict 老数据(无新字段)→ 默认值(免迁移兼容)
4. should_forget 三档:手动 T2 永不 / T1 看 useful_score / T0 看 retain_score;自动档由 useful_score;locked 豁免
5. on_turn_complete RL:本轮 score>=85 召回记忆 useful_score += δ;<60 -= δ;手动档/锁定不动
6. 批次1止血(2026-11-08):P0-1 每轮评分回流(脱离节拍门控) / P0-2 episodic span 真实 ts+
   摘要吃满 span+extract 去二次截断 / P0-3 core 写 source_mid+上限淘汰+遗忘/删除联动清理

日期: 2026-08-13

2026-11-08
变更说明：
  1. P0-4(A4 解耦):useful_score init 断言 0.8→0.5;新增批次1止血测试 8 条(P0-1/P0-2/P0-3)
"""
import json
from types import SimpleNamespace

from memory.encoder import _parse_facts
from memory.models import MemoryItem, Category, ForgetConfig, CoreFact
from memory.forgetting import should_forget, _auto_tier
from memory.coordinator import MemoryCoordinator


# —— 1. _parse_facts 解析 reason/tags ——
def test_parse_facts_with_reason_tags():
    """三要素:_parse_facts 解析 reason + tags(缺省/非list 容错)"""
    text = json.dumps([
        {"content": "用户喜欢动漫", "importance": 0.8, "category": "preference",
         "reason": "用户多次主动提起", "tags": ["喜好", "日常"]},
        {"content": "用户会编程", "importance": 0.5, "category": "fact"},   # 无 reason/tags
        {"content": "异常标签", "importance": 0.5, "tags": "不是数组"},     # tags 非 list
    ])
    facts = _parse_facts(text)
    assert len(facts) == 3
    assert facts[0]["reason"] == "用户多次主动提起"
    assert facts[0]["tags"] == ["喜好", "日常"]
    assert facts[1]["reason"] == ""
    assert facts[1]["tags"] == []
    assert facts[2]["tags"] == []   # 非 list 容错为空


# —— 2. _upsert_fact_dedup 新建 + 去重合并 ——
async def test_upsert_new_with_three_fields(fake_redis):
    """新建记忆带 reason/tags/useful_score(useful_score 默认=importance)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    fact = {"content": "用户喜欢动漫", "importance": 0.8, "emotion": 0.0,
            "category": "preference", "reason": "多次提及", "tags": ["喜好"]}
    written = await c._upsert_fact_dedup("u1", fact)
    assert written is True
    from memory import store
    items = await store.get_all_long_term(fake_redis, "u1")
    assert len(items) == 1
    assert items[0].reason == "多次提及"
    assert items[0].tags == ["喜好"]
    # 2026-11-08 P0-4(A4 解耦):init 默认 0.5,不再冒用 importance(0.8 出生即 T2 已废除)
    assert abs(items[0].useful_score - 0.5) < 1e-6


async def test_upsert_dedup_merge_three_fields(fake_redis):
    """去重合并:reason 取非空者 / tags 并集 / useful_score 取 max(巩固)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.6,
                                      "category": "preference", "reason": "", "tags": ["喜好"]})
    # 第二次命中去重(同内容),新 reason 非空 + 新 tag + 高 useful_score
    written = await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.7,
                                                "category": "preference",
                                                "reason": "用户多次主动提起",
                                                "tags": ["日常", "喜好"]})
    assert written is False   # 命中去重
    from memory import store
    items = await store.get_all_long_term(fake_redis, "u1")
    assert len(items) == 1
    m = items[0]
    assert m.reason == "用户多次主动提起"          # 旧空→取新非空
    assert set(m.tags) == {"喜好", "日常"}          # 并集
    assert abs(m.importance - 0.7) < 1e-6          # max
    assert m.access_count == 1                      # 命中 +1


# —— 3. 兼容性:老数据免迁移 ——
def test_from_dict_legacy_compat():
    """老 JSON(无 reason/tags/useful_score/tier)→ from_dict 补默认,免迁移"""
    raw = {
        "id": "mem_x", "content": "老记忆", "category": "fact",
        "importance": 0.5, "emotion": 0.0,
        "created_ts": 1, "last_access_ts": 1, "access_count": 0,
        "forgotten": False, "source": "dialog", "locked": False,
    }
    m = MemoryItem.from_dict(raw)
    assert m.reason == ""
    assert m.tags == []
    assert abs(m.useful_score - 0.5) < 1e-6
    assert m.tier == -1


# —— 4. 三档衰减判定 ——
def _cfg():
    return ForgetConfig(tier0_threshold=0.3, tier1_threshold=0.7, retain_threshold=0.3)


def test_auto_tier_by_useful_score():
    """自动档:useful_score→T2/T1/T0(由 _auto_tier 推)"""
    cfg = _cfg()
    assert _auto_tier(MemoryItem(id="a", content="x", useful_score=0.9), cfg) == 2
    assert _auto_tier(MemoryItem(id="b", content="x", useful_score=0.5), cfg) == 1
    assert _auto_tier(MemoryItem(id="c", content="x", useful_score=0.1), cfg) == 0


def test_should_forget_manual_tier2_never():
    """手动 T2 永不遗忘(useful_score 很低也不忘)"""
    cfg = _cfg()
    m = MemoryItem(id="x", content="x", useful_score=0.01, tier=2)
    assert should_forget(m, cfg) is False


def test_should_forget_manual_tier1_by_useful_score():
    """手动 T1:只在 useful_score 跌破 tier0_threshold 才忘"""
    cfg = _cfg()
    m_ok = MemoryItem(id="x", content="x", useful_score=0.5, tier=1)
    assert should_forget(m_ok, cfg) is False           # 高分不忘
    m_low = MemoryItem(id="x", content="x", useful_score=0.1, tier=1)
    assert should_forget(m_low, cfg) is True           # 跌破→忘


def test_should_forget_locked_exempt():
    """locked 强制永不(即便 T0 衰减也不忘)"""
    cfg = _cfg()
    m = MemoryItem(id="x", content="x", useful_score=0.0, tier=0, locked=True)
    assert should_forget(m, cfg) is False


def test_should_forget_auto_tier0_natural_decay():
    """自动 T0(useful_score 低):retain_score 跌破阈值→忘(老逻辑保留)"""
    cfg = _cfg()
    # access_count=0/importance 低/很久没访问 → retain_score 极低
    m = MemoryItem(id="x", content="x", useful_score=0.05, importance=0.0,
                   created_ts=1, last_access_ts=1)   # ts=1 = 很久以前
    assert should_forget(m, cfg) is True


# —— 5. on_turn_complete RL useful_score 增减 ——
async def test_rl_useful_score_high_score_reinforce(fake_redis, monkeypatch):
    """本轮 score>=85 → 被召回记忆 useful_score += δ(强化)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    # 预置一条记忆 + 标记为本轮召回
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.5,
                                      "category": "preference"})   # useful_score=0.5
    from memory import store
    items = await store.get_all_long_term(fake_redis, "u1")
    mid = items[0].id

    class FakeCtx:
        object_id = "u1"
        last_score = 90.0                    # >=85 强化
        memory_meta = {"hit_mids": [mid]}    # 本轮召回了这条

    from core.config import settings
    monkeypatch.setattr(settings, "memory_useful_score_delta", 0.1)
    async with c._lock("u1"):
        await c._apply_score_to_recalled("u1", FakeCtx(), sign=1)

    m = await store.get_long_term(fake_redis, "u1", mid)
    assert abs(m.useful_score - 0.6) < 1e-6   # 0.5 + 0.1


async def test_rl_useful_score_manual_tier_skipped(fake_redis, monkeypatch):
    """手动档 tier>=0 的记忆:RL 增减跳过(不动用户显式设定)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    from memory import store
    from memory.models import MemoryItem, Category
    item = MemoryItem(id="mem_manual", content="手动", category=Category.FACT,
                      importance=0.5, useful_score=0.5, tier=2)   # 手动 T2
    await store.upsert_long_term(fake_redis, "u1", item)

    class FakeCtx:
        object_id = "u1"
        last_score = 90.0
        memory_meta = {"hit_mids": ["mem_manual"]}

    from core.config import settings
    monkeypatch.setattr(settings, "memory_useful_score_delta", 0.1)
    async with c._lock("u1"):
        await c._apply_score_to_recalled("u1", FakeCtx(), sign=1)

    m = await store.get_long_term(fake_redis, "u1", "mem_manual")
    assert abs(m.useful_score - 0.5) < 1e-6   # 未动


# —— 6. 批次1止血(P0-1/P0-2/P0-3,2026-11-08)——
class _CaptureLLM:
    """捕获 prompt 的 mock LLM(验 prompt 内容用;chat 返回预设 text)"""
    name = "capture"

    def __init__(self, text: str = "摘要文本"):
        self.text = text
        self.prompt = ""

    async def chat(self, messages, model="", **opts):
        self.prompt = messages[0].content

        class _R:
            pass
        _R.text = self.text
        return _R()


async def test_rl_reflux_every_turn_outside_beat(fake_redis, monkeypatch):
    """P0-1:评分回流脱离「if facts + 每 6 轮节拍」双重门控——非节拍轮也回流(5/6 评分信号不再丢)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.5,
                                      "category": "preference"})   # useful_score=0.5
    from memory import store
    mid = (await store.get_all_long_term(fake_redis, "u1"))[0].id

    import memory.store as mstore

    async def _turn1(redis, oid):
        return 1   # 不在 12/6 节拍上(旧版此轮啥都不触发)

    monkeypatch.setattr(mstore, "get_turn_count", _turn1)

    class FakeCtx:
        object_id = "u1"
        last_score = 30.0                     # <60 → 衰减
        memory_meta = {"hit_mids": [mid]}
        created_ts = 0
        persona_card = None

    from core.config import settings
    monkeypatch.setattr(settings, "memory_useful_score_delta", 0.1)
    await c.on_turn_complete(FakeCtx())
    m = await store.get_long_term(fake_redis, "u1", mid)
    assert abs(m.useful_score - 0.4) < 1e-6   # 0.5 - 0.1(旧版此轮分数不动)


async def test_rl_reflux_middle_band_noop(fake_redis, monkeypatch):
    """P0-1:60<=score<85 中间带 sign=0,回流零操作(分数不动)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.5,
                                      "category": "preference"})
    from memory import store
    mid = (await store.get_all_long_term(fake_redis, "u1"))[0].id

    import memory.store as mstore

    async def _turn1(redis, oid):
        return 1

    monkeypatch.setattr(mstore, "get_turn_count", _turn1)

    class FakeCtx:
        object_id = "u1"
        last_score = 70.0                     # 中间带
        memory_meta = {"hit_mids": [mid]}
        created_ts = 0
        persona_card = None

    await c.on_turn_complete(FakeCtx())
    m = await store.get_long_term(fake_redis, "u1", mid)
    assert abs(m.useful_score - 0.5) < 1e-6   # 未动


async def test_episodic_span_ts_real_window(fake_redis, monkeypatch):
    """P0-2(修 B2):episodic span ts 取窗口首尾消息真实 ts(不再双填 created_ts)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    span = [SimpleNamespace(role="user", content="我今天去了海边", ts=1700000000000),
            SimpleNamespace(role="assistant", content="听起来很开心", ts=1700000060000),
            SimpleNamespace(role="user", content="下次带你去", ts=1700000120000)]

    import memory.store as mstore

    async def _turn12(redis, oid):
        return 12   # 命中 summarize 节拍(threshold=12)

    async def _span(redis, oid, turns):
        return span

    monkeypatch.setattr(mstore, "get_turn_count", _turn12)
    monkeypatch.setattr(mstore, "get_working_span", _span)

    class FakeCtx:
        object_id = "u1"
        created_ts = 9999999999999   # 原版会把 span 两端都填成它
        last_score = -1.0
        persona_card = None
        memory_meta = {"hit_mids": []}

    await c.on_turn_complete(FakeCtx())
    from memory import store
    epis = await store.get_episodic(fake_redis, "u1", limit=5)
    assert len(epis) == 1
    assert epis[0].span_start_ts == 1700000000000   # 窗口首条真实 ts
    assert epis[0].span_end_ts == 1700000120000     # 窗口末条真实 ts(非 created_ts)


async def test_summarize_full_span_coverage():
    """P0-2(修 A2):summarize 吃满整个 span(原版 [-6:] 硬截,75% 窗口内容进不了情景记忆)"""
    from memory import encoder
    msgs = [SimpleNamespace(role=("user" if i % 2 == 0 else "assistant"),
                            content=f"内容{i}", ts=1000 + i) for i in range(8)]
    cap = _CaptureLLM()
    summary = await encoder.summarize(msgs, cap, "", user_alias="")
    assert summary == "摘要文本"
    assert "内容0" in cap.prompt    # 窗口头部(旧版 [-6:] 截掉)
    assert "内容7" in cap.prompt    # 窗口尾部


async def test_extract_batch_no_hidden_truncation():
    """P0-2(review #4):extract_facts_batch 去 [-12:] 二次截断——span 头部也进 prompt;单条 200 字限长"""
    from memory import encoder
    msgs = [SimpleNamespace(role=("user" if i % 2 == 0 else "assistant"),
                            content=f"消息{i}的内容") for i in range(14)]
    cap = _CaptureLLM(text="[]")
    facts = await encoder.extract_facts_batch(msgs, cap, "", user_alias="")
    assert facts == []
    assert "消息0的内容" in cap.prompt     # 头部(旧版 [-12:] 截掉前 2 条)
    assert "消息13的内容" in cap.prompt

    long_content = "长" * 300
    await encoder.extract_facts_batch([SimpleNamespace(role="user", content=long_content)], cap, "")
    assert long_content not in cap.prompt  # 300 字未整段进入
    assert "长" * 200 in cap.prompt        # 单条 200 字限长生效


async def test_core_source_mid_and_cap_eviction(fake_redis, monkeypatch):
    """P0-3:core 写 source_mid(反查 long_term)+ max_core 上限淘汰最旧非 locked"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    from memory import store
    from core.config import settings
    monkeypatch.setattr(settings, "memory_max_core", 2)
    # 三条 long 记忆(供 source_mid 反查;importance 0.5 不自动升 core,便于手动控制)
    # 内容两两低字符重叠——降级去重是单字 Jaccard≥0.3,共享"事实"等常用字会被误判重复(D4 已知)
    for content in ["主人住在杭州", "主人喜欢摄影", "主人养了一只橘猫"]:
        await c._upsert_fact_dedup("u1", {"content": content, "importance": 0.5,
                                          "category": "preference"})
    for content in ["主人住在杭州", "主人喜欢摄影", "主人养了一只橘猫"]:
        await c._upsert_core_fact("u1", {"content": content, "category": "preference"})
    core = await store.get_core(fake_redis, "u1")
    assert len(core) == 2                     # 上限=2,最旧的"主人住在杭州"被淘汰
    assert all(cf.source_mid for cf in core)  # source_mid 反查成功(非空)
    assert "主人住在杭州" not in [cf.content for cf in core]
    assert "主人养了一只橘猫" in [cf.content for cf in core]


async def test_core_cap_locked_exempt(fake_redis, monkeypatch):
    """P0-3:上限淘汰 locked 豁免(最旧条目 locked 时跳过,淘汰次旧)"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    from memory import store
    from core.config import settings
    monkeypatch.setattr(settings, "memory_max_core", 2)
    # 预置 locked 的"主人住在杭州"(无 source_mid 也可,锁定即豁免;内容两两低重叠防误判重复)
    await store.set_core(fake_redis, "u1", [
        CoreFact(key="fact:juzhou", content="主人住在杭州", locked=True)])
    await c._upsert_core_fact("u1", {"content": "主人喜欢摄影", "category": "fact"})
    await c._upsert_core_fact("u1", {"content": "主人养了一只橘猫", "category": "fact"})
    core = await store.get_core(fake_redis, "u1")
    assert [cf.content for cf in core] == ["主人住在杭州", "主人养了一只橘猫"]   # locked 甲保留,乙被淘汰


async def test_core_prune_on_forget_and_delete(fake_redis):
    """P0-3:遗忘/物理删除联动清理 core(source_mid 命中即移除,修记忆鬼影);恢复不回填"""
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    from memory import store
    # 遗忘路径
    await c._upsert_fact_dedup("u1", {"content": "用户在杭州工作", "importance": 0.5,
                                      "category": "fact"})
    mid = (await store.get_all_long_term(fake_redis, "u1"))[0].id
    await c._upsert_core_fact("u1", {"content": "用户在杭州工作", "category": "fact"})
    core = await store.get_core(fake_redis, "u1")
    assert len(core) == 1 and core[0].source_mid == mid   # 反查命中
    await store.mark_forgotten(fake_redis, "u1", [mid])
    assert await store.get_core(fake_redis, "u1") == []   # 遗忘联动清除

    # 物理删除路径(换一条新记忆,避免遗忘态干扰反查)
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢爬山", "importance": 0.5,
                                      "category": "fact"})
    mid2 = [m.id for m in await store.get_all_long_term(fake_redis, "u1")
            if m.content == "用户喜欢爬山"][0]
    await c._upsert_core_fact("u1", {"content": "用户喜欢爬山", "category": "fact"})
    await store.delete_long_term(fake_redis, "u1", [mid2])
    assert await store.get_core(fake_redis, "u1") == []   # 删除联动清除
