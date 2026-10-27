"""
worldbook 纯逻辑单测(docs/09 §1-§2):归一化匹配/正则/secondary AND/候选收集/
过滤(enabled/冷却/概率)/排序(position/order/weight/久未命中)/预算裁剪(always 永不裁
+前 3 trigger 保底+max_entries 硬顶)/渲染/一站式/记账/模型容错。零 IO,纯函数直测。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新增:纯逻辑全路径单测
"""
import random

from memory.worldbook import (
    WbEntry, normalize_for_match, estimate_tokens, auto_keys, match_entry,
    collect_candidates, filter_entries, sort_entries, budget_trim,
    render_sections, select_for_injection, merge_stats, TRIGGER_KEEP_MIN,
)

NOW = 1_800_000_000_000


def _e(eid="wb_x", **kw) -> WbEntry:
    """造条目:默认 trigger/启用/keys 空"""
    d = dict(id=eid, content="内容", keys=[], mode="trigger", enabled=True)
    d.update(kw)
    return WbEntry(**d)


class _Rng1:
    """random.Random 替身:random() 恒返 0.5(<probability=1 过,>0.5 不过)"""
    def random(self):
        return 0.5


class _Rng0:
    """random.Random 替身:random() 恒返 0.9"""
    def random(self):
        return 0.9


# ================ 归一化 / 估算 / 自动 keys ================

def test_normalize_fullwidth_case_whitespace():
    """全角→半角、大写→小写、去空白(全角空格也去)"""
    assert normalize_for_match("Ｔｈｕｎｄｅｒ") == "thunder"
    assert normalize_for_match("  打 雷 \t\n") == "打雷"
    assert normalize_for_match("Ａｂｃ　Ｄｅｆ") == "abcdef"
    assert normalize_for_match("") == ""


def test_estimate_tokens_mixed():
    """汉字 1/字 + 英文词 1.3/词,至少 1"""
    assert estimate_tokens("打雷") == 2
    assert estimate_tokens("thunder storm") == 3   # 2 词 ×1.3 = 2.6 → round 3
    assert estimate_tokens("怕thunder") == 2        # 1 + 1.3 = 2.3 → round 2
    assert estimate_tokens("") == 1


def test_estimate_tokens_entry_autofill():
    """WbEntry 未填 token_estimate 时按 content 自动估算"""
    e = WbEntry(id="wb_t", content="打雷了", token_estimate=0)
    assert e.token_estimate == estimate_tokens("打雷了") == 3


def test_auto_keys_chinese_bigram_and_words():
    """中文 2-gram + 英文词(长度>=2);虚词 2-gram 被停用表过滤"""
    ks = auto_keys("她怕打雷,喜欢 thunder 和 AC 丝", limit=10)
    assert "打雷" in ks and "怕打" in ks
    assert "thunder" in ks and "ac" in ks    # 2 字母词也在收录范围
    assert all(k not in ks for k in ("我们", "一个"))
    # 默认 limit=6:中文先填满,超限截断
    assert len(auto_keys("她怕打雷,喜欢 thunder 和 AC 丝")) == 6


def test_auto_keys_stopgram_filtered():
    """停用 2-gram 不出 keys(滑窗组合仍会产生非停用邻居组合)"""
    ks = auto_keys("我们没有说什么")
    assert "我们" not in ks and "没有" not in ks and "什么" not in ks
    assert ks   # "们没/有说/说什"等邻居组合仍在


def test_auto_keys_limit_and_dedup():
    """保序去重 + limit 截断"""
    ks = auto_keys("打雷打雷下雨", limit=2)
    assert len(ks) == 2 and ks[0] == "打雷"


# ================ 匹配 ================

def test_match_keys_substring_normalized():
    """keys 子串命中(全半角/大小写不敏感)"""
    e = _e(keys=["打雷", "thunder"])
    assert match_entry(e, ["外面 THUNDER 好大声"])
    assert match_entry(e, ["打雷了"])
    assert not match_entry(e, ["今天天气不错"])
    assert not match_entry(e, [""])


def test_match_recent_turns_texts():
    """匹配文本含最近对话(命中其一即可)"""
    e = _e(keys=["雷声"])
    assert match_entry(e, ["没说什么", "刚才雷声好吓人"])


def test_match_regex_priority_and_fallback():
    """key_regex 优先命中;regex 未命中回退 keys;非法正则回退 keys 不炸"""
    e = _e(keys=["打雷"], key_regex="雷声.+")
    assert match_entry(e, ["昨晚雷声好大"])        # regex 命中
    assert match_entry(e, ["打雷了"])             # regex 未命中("打雷了"无"雷声"),回退 keys 命中
    bad = _e(keys=["打雷"], key_regex="([invalid")
    assert match_entry(bad, ["打雷了"])           # 非法正则视为不命中,回退 keys
    miss = _e(keys=["下雨"], key_regex="雷声")
    assert not match_entry(miss, ["打雷了"])      # regex 未命中 + keys 未命中


def test_match_secondary_keys_and():
    """secondary_keys 非空时须全部命中(AND 门)"""
    e = _e(keys=["打雷"], secondary_keys=["晚上"])
    assert match_entry(e, ["晚上打雷"])
    assert not match_entry(e, ["白天打雷"])
    assert not match_entry(e, ["晚上下雨"])


# ================ 收集 / 过滤 ================

def test_collect_candidates_always_and_trigger():
    """always 全收(无论命中)+ trigger 命中才收"""
    a1 = _e("a1", mode="always")
    t1 = _e("t1", keys=["打雷"])
    t2 = _e("t2", keys=["下雨"])
    got = collect_candidates([a1, t1, t2], ["打雷了"])
    assert [e.id for e in got] == ["a1", "t1"]


def test_filter_enabled_cooldown_probability():
    """enabled=false 跳过 / 冷却未过跳过 / trigger 按概率(rng 注入确定性)"""
    dis = _e("dis", keys=["打雷"], enabled=False)
    hot = _e("hot", keys=["打雷"], cooldown_minutes=30, last_injected_at=NOW - 10 * 60_000)
    cold = _e("cold", keys=["打雷"], cooldown_minutes=30, last_injected_at=NOW - 31 * 60_000)
    p0 = _e("p0", keys=["打雷"], probability=0.0)
    # p0 的 rng.random()=0.5 >= 0 → 刷掉
    got = filter_entries([dis, hot, cold, p0], NOW, rng=_Rng1())
    assert [e.id for e in got] == ["cold"]


def test_filter_probability_always_exempt():
    """always 条目不受概率影响(rng 恒 0.9 仍保留)"""
    a = _e("a", mode="always", probability=0.1)
    got = filter_entries([a], NOW, rng=_Rng0())
    assert [e.id for e in got] == ["a"]


# ================ 排序 ================

def test_sort_position_order_weight_lasthit():
    """position 分组序 → 组内 order 升序 → weight 降序 → last_hit_at 升序"""
    tail_low = _e("t1", position="tail", order=10)
    head_high = _e("t2", position="before_persona", order=100)
    head_low = _e("t3", position="before_persona", order=1)
    head_ord_hi_w = _e("t4", position="before_persona", order=50, weight=0.9)
    head_ord_lo_w = _e("t5", position="before_persona", order=50, weight=0.5)
    got = sort_entries([tail_low, head_high, head_low, head_ord_hi_w, head_ord_lo_w])
    # t4/t5 同 order:weight 0.9 > 0.5 → t4 在前
    assert [e.id for e in got] == ["t3", "t4", "t5", "t2", "t1"]


def test_sort_lasthit_tiebreak():
    """weight 相同时久未命中(last_hit_at 小/0)优先"""
    fresh = _e("fresh", last_hit_at=NOW)
    never = _e("never", last_hit_at=0)
    old = _e("old", last_hit_at=NOW - 1000)
    got = sort_entries([fresh, never, old])
    assert [e.id for e in got] == ["never", "old", "fresh"]


# ================ 预算裁剪 ================

def test_budget_trim_always_never_dropped():
    """always 永不被裁(验收#3):预算极小仍全保留"""
    always = [_e(f"a{i}", mode="always", content="设定" * 50) for i in range(5)]
    kept, dropped = budget_trim(sort_entries(always), budget=10)
    assert len(kept) == 5 and not dropped


def test_budget_trim_trigger_floor_three():
    """前 3 条 trigger 无视预算保底,之后的按预算(中文逐字计 token,各 20)"""
    trigs = [_e(f"t{i}", content="雷" * 20) for i in range(8)]   # 各 20 token
    kept, dropped = budget_trim(trigs, budget=60)
    assert len(kept) == TRIGGER_KEEP_MIN   # 3 保底已用 60,第 4 条 80>60 跳过
    assert len(dropped) == 5


def test_budget_trim_fits_small_later_entry():
    """保底 3 条之后的:超预算跳过该条但不 break,更小的后续条仍可进"""
    floors = [_e(f"floor{i}", content="电" * 3) for i in range(3)]   # 各 3,保底已用 9
    big = _e("big", content="雷" * 100)      # 100 token,放不进
    small = _e("small", content="雨" * 5)    # 5 token,9+5=14 <= 15 可进
    kept, _ = budget_trim(floors + [big, small], budget=15)
    ids = [e.id for e in kept]
    assert all(f"floor{i}" in ids for i in range(3))
    assert "small" in ids and "big" not in ids


def test_budget_trim_max_entries_hard_cap():
    """max_entries 硬顶:always 优先占位,余量给 trigger"""
    always = [_e(f"a{i}", mode="always") for i in range(3)]
    trigs = [_e(f"t{i}", content="x" * 3) for i in range(5)]
    kept, dropped = budget_trim(sort_entries(always + trigs), budget=10_000, max_entries=5)
    kept_ids = {e.id for e in kept}
    assert len(kept) == 5
    assert all(f"a{i}" in kept_ids for i in range(3))       # always 全保
    assert len([i for i in kept_ids if i.startswith("t")]) == 2
    assert len(dropped) == 3


def test_budget_trim_max_entries_always_only():
    """always 数量本身超 max_entries 的极端场景:always 也截(硬顶否则永不成立)"""
    always = [_e(f"a{i}", mode="always") for i in range(6)]
    kept, _ = budget_trim(always, budget=10_000, max_entries=4)
    assert len(kept) == 4 and all(e.mode == "always" for e in kept)


# ================ 渲染 / 一站式 ================

def test_render_sections_groups_and_lines():
    """每条 `- {content}`(无标题),按 position 分组"""
    e1 = _e("e1", content="甲", position="after_persona")
    e2 = _e("e2", content="乙", position="after_persona")
    e3 = _e("e3", content="丙", position="tail")
    sec = render_sections([e1, e2, e3])
    assert sec == {"after_persona": "- 甲\n- 乙", "tail": "- 丙"}


def test_select_for_injection_end_to_end():
    """一站式:命中→过滤→排序→裁剪→渲染→统计。
    disabled 条目也会进候选(hit_ids 含它)但被 enabled 过滤(docs §2.2 过滤阶段)"""
    a = _e("a", mode="always", content="常驻", position="after_persona")
    hit = _e("hit", keys=["打雷"], content="打雷相关", position="before_memories")
    miss = _e("miss", keys=["下雨"], content="下雨相关")
    dis = _e("dis", keys=["打雷"], content="停用", enabled=False)
    r = select_for_injection([a, hit, miss, dis], ["打雷了"], NOW,
                             budget=2000, max_entries=12, rng=random.Random(42))
    assert set(r["sections"]) == {"after_persona", "before_memories"}
    assert r["sections"]["after_persona"] == "- 常驻"
    assert [e.id for e in r["kept"]] == ["a", "hit"]
    assert r["hit_ids"] == ["a", "hit", "dis"]   # collect 不筛 enabled,dis 命中入候选
    assert r["tokens"] == sum(e.token_estimate for e in r["kept"])


def test_merge_stats_hit_vs_injected():
    """命中未注入只刷 last_hit_at;注入的 hits+1 且三时间戳全刷"""
    e = _e()
    merge_stats(e, hit=True, now_ms=NOW)
    assert e.last_hit_at == NOW and e.hits == 0 and e.last_injected_at == 0
    merge_stats(e, injected=True, now_ms=NOW + 1)
    assert e.hits == 1 and e.last_injected_at == NOW + 1 and e.last_hit_at == NOW + 1


# ================ 模型容错 ================

def test_from_dict_invalid_enum_and_json_string_lists():
    """非法 mode/position/source 回退默认;Redis 读回的 JSON 字符串 list 可解析"""
    e = WbEntry.from_dict({
        "id": "wb_r", "content": "c", "mode": "weird", "position": "nowhere",
        "source": "alien", "keys": '["打雷", "雷声"]', "secondary_keys": "not-json",
        "probability": 2.0, "cooldown_minutes": -5,
    })
    assert e.mode == "trigger" and e.position == "before_memories" and e.source == "manual"
    assert e.keys == ["打雷", "雷声"]
    assert e.secondary_keys == []
    assert e.probability == 1.0 and e.cooldown_minutes == 0


def test_to_redis_list_fields_jsonified():
    """to_redis 的 list 字段 JSON 化(hash 值只接受标量),from_dict 能读回"""
    e = _e(keys=["打雷"], secondary_keys=["晚上"])
    d = e.to_redis()
    assert isinstance(d["keys"], str) and isinstance(d["secondary_keys"], str)
    back = WbEntry.from_dict(d)
    assert back.keys == ["打雷"] and back.secondary_keys == ["晚上"]
    assert back.to_dict() == e.to_dict()
