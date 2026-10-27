"""
proactive_reply 插件单测
覆盖:静默时段(跨零点)/每日上限/最小间隔/空闲阈值/概率 五重门控纯函数;
on_tick 全链(命中发送+记状态/各门拦截/自然日切换计数归零/软失败不外抛/use_tts 透传);
generate_opener 组装口径(人设渲染+mood hint+契约压轴+最近对话+指令);plugin.yaml 默认关闭。

日期: 2026-10-25

2026-10-25
变更说明：
  1. 新增 proactive_reply 插件测试(门控纯函数 + on_tick 链路 + 生成组装 + manifest 校验)
  2. 对抗审查修正后补测:系统级静默拦截/参数脏类型 fail-closed/布尔归一;
     下发异常语义改为"状态照记防无界重试"

2026-10-27
变更说明：
  1. 晚安事故修复配套:is_farewell 纯函数/on_tick 道别静默+再开口解除+farewell_aware
     可关/指令含禁编造约束 断言;manifest 增 farewell_aware 键校验
"""
from datetime import datetime
from pathlib import Path

import plugins.proactive_reply.plugin as proactive
from llm.base import Message
from persona.renderer import OUTPUT_CONTRACT
from pipeline.context import MessageContext
from plugins.base import HookResult, PluginContext
from plugins.manifest import PluginManifest, parse_manifest
from plugins.proactive_reply.plugin import (
    ProactiveReplyPlugin,
    _as_bool,
    _sanitize_opener,
    check_gates,
    generate_opener,
    in_quiet_hours,
    is_farewell,
    parse_quiet_hours,
)

# 全门放行基准参数(纯函数侧概率由 roll 显式控制;on_tick 链路侧用 prob=1 保证确定性)
_BASE = {
    "quiet_hours": "23:30-08:00", "daily_max": 3, "min_gap_minutes": 120,
    "idle_minutes": 90, "prob": 0.05, "use_tts": False, "llm_provider": "local",
}
# 固定"现在":2026-10-25 12:00(白天,不在默认静默时段;naive datetime 与 _now() 同口径)
_NOON = datetime(2026, 10, 25, 12, 0, 0)


class _FakeManager:
    """轻量 mock:get_params 返回构造时指定的参数(不走 config_schema 合并,测试显式给全)"""

    def __init__(self, params=None):
        self._params = params or {}

    async def get_params(self, name, oid):
        return dict(self._params)


def _make_plugin(params=None, redis=None):
    """构造插件实例(m6 惯例:手写 pctx 注入,不经 PluginManager)"""
    p = ProactiveReplyPlugin()
    p.manifest = PluginManifest(name="proactive_reply")
    p.pctx = PluginContext(manager=_FakeManager(params), redis=redis,
                           settings=None, manifest=p.manifest)
    return p


def _patch_flow(monkeypatch, *, content="在忙什么呀~", fail_send=False, generate_fail=False):
    """替换生成/下发为记录器(可注入失败),返回调用记录 dict"""
    calls = {"generate": [], "send": []}

    async def fake_generate(redis, oid, provider_name="local"):
        calls["generate"].append((oid, provider_name))
        if generate_fail:
            raise RuntimeError("generate boom")
        return content

    async def fake_send(redis, oid, content_, *, use_tts=None):
        calls["send"].append((oid, content_, use_tts))
        if fail_send:
            raise RuntimeError("send boom")
        return {"proxy_mid": "m1", "delivered": True, "mode": "active"}

    monkeypatch.setattr(proactive, "generate_opener", fake_generate)
    monkeypatch.setattr(proactive, "send_proactive", fake_send)
    return calls


# ================ 纯函数:静默时段解析与判定 ================

def test_parse_quiet_hours_valid_and_invalid():
    """合法输入(含跨零点/带空格)解析为分钟数;非法输入一律 None"""
    assert parse_quiet_hours("23:30-08:00") == (23 * 60 + 30, 8 * 60)
    assert parse_quiet_hours(" 09:00 - 12:00 ") == (9 * 60, 12 * 60)
    for bad in ("", "08:00", "25:00-09:00", "08:70-09:00", "abc-def", "08:00-09:00-10:00"):
        assert parse_quiet_hours(bad) is None, bad


def test_in_quiet_hours_cross_midnight():
    """23:30-08:00 跨零点:深夜与凌晨都静默;白天与 23:29 不静默;起点含/终点不含"""
    q = parse_quiet_hours("23:30-08:00")
    assert in_quiet_hours(datetime(2026, 10, 25, 23, 30), *q) is True    # 起点含
    assert in_quiet_hours(datetime(2026, 10, 25, 23, 45), *q) is True
    assert in_quiet_hours(datetime(2026, 10, 26, 0, 15), *q) is True     # 跨零点后的凌晨
    assert in_quiet_hours(datetime(2026, 10, 26, 7, 59), *q) is True
    assert in_quiet_hours(datetime(2026, 10, 26, 8, 0), *q) is False     # 终点不含
    assert in_quiet_hours(datetime(2026, 10, 25, 12, 0), *q) is False
    assert in_quiet_hours(datetime(2026, 10, 25, 23, 29), *q) is False


def test_in_quiet_hours_same_day_and_empty():
    """同日时段(09:00-12:00)正常判定;起==止视为空时段(永不静默)"""
    q = parse_quiet_hours("09:00-12:00")
    assert in_quiet_hours(datetime(2026, 10, 25, 8, 59), *q) is False
    assert in_quiet_hours(datetime(2026, 10, 25, 9, 0), *q) is True
    assert in_quiet_hours(datetime(2026, 10, 25, 11, 59), *q) is True
    assert in_quiet_hours(datetime(2026, 10, 25, 12, 0), *q) is False
    assert in_quiet_hours(datetime(2026, 10, 25, 3, 0), 480, 480) is False


# ================ 纯函数:五重门控 ================

def test_check_gates_all_pass():
    """全门放行:未达上限/间隔与空闲均过阈值/概率命中"""
    ok, _ = check_gates(_NOON, _BASE, today_count=2,
                        last_sent_ts=_NOON.timestamp() - 121 * 60,
                        last_user_ts=_NOON.timestamp() - 91 * 60, roll=0.0)
    assert ok is True


def test_check_gates_quiet_blocks():
    """凌晨 00:15(跨零点静默段)拦截"""
    ok, why = check_gates(datetime(2026, 10, 26, 0, 15), _BASE,
                          today_count=0, last_sent_ts=None, last_user_ts=None, roll=0.0)
    assert ok is False and "静默" in why


def test_check_gates_daily_max():
    """today_count>=daily_max 拦截;差一条放行;daily_max=0 一律拦截"""
    ok, why = check_gates(_NOON, _BASE, today_count=3, last_sent_ts=None, roll=0.0)
    assert ok is False and "上限" in why
    ok, _ = check_gates(_NOON, _BASE, today_count=2, last_sent_ts=None, roll=0.0)
    assert ok is True
    ok, _ = check_gates(_NOON, {**_BASE, "daily_max": 0},
                        today_count=0, last_sent_ts=None, roll=0.0)
    assert ok is False


def test_check_gates_min_gap_boundary():
    """119 分钟前发过→拦截;恰好 120 分钟整→放行(边界含等值)"""
    ok, why = check_gates(_NOON, _BASE, today_count=0,
                          last_sent_ts=_NOON.timestamp() - 119 * 60, roll=0.0)
    assert ok is False and "间隔" in why
    ok, _ = check_gates(_NOON, _BASE, today_count=0,
                        last_sent_ts=_NOON.timestamp() - 120 * 60, roll=0.0)
    assert ok is True


def test_check_gates_idle():
    """对方 30 分钟前发言→勿扰;恰好 90 分钟整→放行;无记录(None)→视为足够空闲"""
    ok, why = check_gates(_NOON, _BASE, today_count=0, last_sent_ts=None,
                          last_user_ts=_NOON.timestamp() - 30 * 60, roll=0.0)
    assert ok is False and "刚聊过" in why
    ok, _ = check_gates(_NOON, _BASE, today_count=0, last_sent_ts=None,
                        last_user_ts=_NOON.timestamp() - 90 * 60, roll=0.0)
    assert ok is True
    ok, _ = check_gates(_NOON, _BASE, today_count=0, last_sent_ts=None,
                        last_user_ts=None, roll=0.0)
    assert ok is True


def test_check_gates_probability():
    """roll>=prob 拦截/roll<prob 放行;prob=0 时 roll=0 也不放行;roll=None 跳过概率门"""
    ok, why = check_gates(_NOON, _BASE, today_count=0, last_sent_ts=None, roll=0.06)
    assert ok is False and "概率" in why
    ok, _ = check_gates(_NOON, _BASE, today_count=0, last_sent_ts=None, roll=0.049)
    assert ok is True
    ok, _ = check_gates(_NOON, {**_BASE, "prob": 0},
                        today_count=0, last_sent_ts=None, roll=0.0)
    assert ok is False
    ok, _ = check_gates(_NOON, _BASE, today_count=0, last_sent_ts=None, roll=None)
    assert ok is True


def test_check_gates_bad_quiet_config_fails_closed():
    """quiet_hours 配置非法:防扰民原则,直接不放行"""
    ok, _ = check_gates(_NOON, {**_BASE, "quiet_hours": "now-sleep"},
                        today_count=0, last_sent_ts=None, roll=0.0)
    assert ok is False


def test_check_gates_dirty_param_fails_closed():
    """参数类型脏(prob/daily_max 非数值):fail-closed 不放行且不抛异常(防 60s 刷堆栈)"""
    ok, why = check_gates(_NOON, {**_BASE, "prob": "abc"},
                          today_count=0, last_sent_ts=None, roll=0.01)
    assert ok is False and "参数非法" in why
    ok, _ = check_gates(_NOON, {**_BASE, "daily_max": "x"},
                        today_count=0, last_sent_ts=None, roll=0.0)
    assert ok is False


# ================ on_tick 链路 ================

async def test_on_tick_sends_and_records(fake_redis, monkeypatch):
    """全门放行:生成→下发(use_tts=False)→记状态(当日计数+1/时间戳写入/TTL 生效)"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    calls = _patch_flow(monkeypatch, content="在忙什么呀~")
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    result = await p.on_tick(MessageContext(object_id="10001"))
    assert result is HookResult.CONTINUE
    assert calls["generate"] == [("10001", "local")]
    assert calls["send"] == [("10001", "在忙什么呀~", False)]
    assert await fake_redis.get("mychat:proactive:count:10001:20261025") == "1"
    assert await fake_redis.get("mychat:proactive:last:10001") == str(int(_NOON.timestamp()))
    assert await fake_redis.ttl("mychat:proactive:count:10001:20261025") > 0


async def test_on_tick_takeover_silence_blocks(fake_redis, monkeypatch):
    """系统级静默优先于一切门控:AI 静默模式开/手动静默窗内,其余门全放行也绝不主动搭话"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    await fake_redis.set("mychat:takeover:enabled:10001", "1")          # AI 静默模式开
    await fake_redis.set("mychat:takeover:silence:10002", "1", ex=600)  # 手动静默窗内
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    await p.on_tick(MessageContext(object_id="10002"))
    assert calls["generate"] == [] and calls["send"] == []


async def test_on_tick_prob_zero_never_sends(fake_redis, monkeypatch):
    """prob=0:其余门全放行也绝不生成/发送/写状态"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 0.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert calls["generate"] == [] and calls["send"] == []
    assert await fake_redis.get("mychat:proactive:count:10001:20261025") is None
    assert await fake_redis.get("mychat:proactive:last:10001") is None


async def test_on_tick_quiet_hours_blocks(fake_redis, monkeypatch):
    """23:45(静默时段)拦截:不生成不发送"""
    monkeypatch.setattr(proactive, "_now", lambda: datetime(2026, 10, 25, 23, 45))
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert calls["generate"] == [] and calls["send"] == []


async def test_on_tick_daily_max_blocks(fake_redis, monkeypatch):
    """当日计数已达 3:拦截"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    calls = _patch_flow(monkeypatch)
    await fake_redis.set("mychat:proactive:count:10001:20261025", "3")
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert calls["send"] == []


async def test_on_tick_min_gap_blocks(fake_redis, monkeypatch):
    """30 分钟前刚发过(最小间隔 120):拦截"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    calls = _patch_flow(monkeypatch)
    await fake_redis.set("mychat:proactive:last:10001", int(_NOON.timestamp() - 30 * 60))
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert calls["send"] == []


async def test_on_tick_idle_blocks_when_user_recent(fake_redis, monkeypatch):
    """对方 30 分钟前刚发过消息:勿扰(走真实 chat_store 扫描路径)"""
    from storage import chat_store
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    await chat_store.append_message(fake_redis, "10001", sender="user", content="在吗",
                                    ts=int((_NOON.timestamp() - 30 * 60) * 1000))
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert calls["generate"] == [] and calls["send"] == []


async def test_on_tick_idle_allows_when_user_long_gone(fake_redis, monkeypatch):
    """对方 2 小时前最后发言:放行;更近的 proxy 自发消息不算'对方刚聊过'"""
    from storage import chat_store
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    await chat_store.append_message(fake_redis, "10001", sender="user", content="早",
                                    ts=int((_NOON.timestamp() - 120 * 60) * 1000))
    await chat_store.append_message(fake_redis, "10001", sender="proxy", content="嗯嗯",
                                    ts=int((_NOON.timestamp() - 10 * 60) * 1000))
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert len(calls["send"]) == 1


async def test_on_tick_day_rollover_resets_count(fake_redis, monkeypatch):
    """自然日切换:昨日计数不拦今日(按日期分键),今日从 1 重计"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    await fake_redis.set("mychat:proactive:count:10001:20261024", "3")
    await fake_redis.set("mychat:proactive:last:10001", int(_NOON.timestamp() - 5 * 3600))
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert len(calls["send"]) == 1
    assert await fake_redis.get("mychat:proactive:count:10001:20261025") == "1"
    assert await fake_redis.get("mychat:proactive:count:10001:20261024") == "3"   # 昨日键不动


async def test_on_tick_generate_empty_skips(fake_redis, monkeypatch):
    """生成为空:跳过发送,不写状态(别发空消息)"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    calls = _patch_flow(monkeypatch, content="")
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert calls["generate"] and calls["send"] == []
    assert await fake_redis.get("mychat:proactive:count:10001:20261025") is None


async def test_on_tick_generate_raises_soft_fail(fake_redis, monkeypatch):
    """生成抛异常:on_tick 不外抛(软失败),返回 CONTINUE,状态不写"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    calls = _patch_flow(monkeypatch, generate_fail=True)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    result = await p.on_tick(MessageContext(object_id="10001"))
    assert result is HookResult.CONTINUE
    assert calls["send"] == []


async def test_on_tick_send_raises_soft_fail(fake_redis, monkeypatch):
    """下发抛异常:on_tick 不外抛(软失败),但状态照记(宁可少发不重发,防无界重试刷屏)"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    calls = _patch_flow(monkeypatch, fail_send=True)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    result = await p.on_tick(MessageContext(object_id="10001"))
    assert result is HookResult.CONTINUE
    assert calls["send"]
    assert await fake_redis.get("mychat:proactive:count:10001:20261025") == "1"   # 计数照记
    assert await fake_redis.get("mychat:proactive:last:10001") is not None        # 间隔锚点照记


async def test_on_tick_use_tts_param_forwarded(fake_redis, monkeypatch):
    """use_tts=true 透传给 send_proactive"""
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0, "use_tts": True}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert calls["send"][0][2] is True


# ================ 晚安感知门控(2026-10-27 事故修复) ================

def test_is_farewell_words():
    """道别词命中:晚安(含~后缀)/睡了/困了/好梦/休息了;非道别语不命中;
    反说"不睡了"也命中——方向保守(误判只会少发,防扰民同向)"""
    assert is_farewell("晚安～") is True
    assert is_farewell("我先睡了") is True
    assert is_farewell("困了不行了") is True
    assert is_farewell("做个好梦") is True
    assert is_farewell("去休息了") is True
    assert is_farewell("不睡了") is True            # 反说也命中(保守方向,文档已注明)
    assert is_farewell("在忙什么") is False
    assert is_farewell("早上好") is False
    assert is_farewell("") is False
    assert is_farewell(None) is False               # 容错:None/空不炸不误判


async def test_on_tick_farewell_blocks(fake_redis, monkeypatch):
    """对方 3 小时前道过晚安(末条用户消息=道别):其余门全放行也绝不主动搭话
    (事故场景复现:01:59 道晚安→静默 7h40m→09:30 静默段一结束就补发"早上好")"""
    from storage import chat_store
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    await chat_store.append_message(fake_redis, "10001", sender="user", content="晚安～",
                                    ts=int((_NOON.timestamp() - 3 * 3600) * 1000))
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert calls["generate"] == [] and calls["send"] == []
    assert await fake_redis.get("mychat:proactive:count:10001:20261025") is None   # 未记账


async def test_on_tick_farewell_lifts_when_user_returns(fake_redis, monkeypatch):
    """道别后又发言(末条不再是道别语):门控自然解除,恢复可主动"""
    from storage import chat_store
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    await chat_store.append_message(fake_redis, "10001", sender="user", content="晚安～",
                                    ts=int((_NOON.timestamp() - 4 * 3600) * 1000))
    await chat_store.append_message(fake_redis, "10001", sender="user", content="早",
                                    ts=int((_NOON.timestamp() - 2 * 3600) * 1000))
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert len(calls["send"]) == 1


async def test_on_tick_farewell_disabled_by_param(fake_redis, monkeypatch):
    """farewell_aware=false 显式关闭:道别静默不生效(旧行为,供面板关停对比)"""
    from storage import chat_store
    monkeypatch.setattr(proactive, "_now", lambda: _NOON)
    await chat_store.append_message(fake_redis, "10001", sender="user", content="晚安～",
                                    ts=int((_NOON.timestamp() - 3 * 3600) * 1000))
    calls = _patch_flow(monkeypatch)
    p = _make_plugin({**_BASE, "prob": 1.0, "farewell_aware": False}, redis=fake_redis)
    await p.on_tick(MessageContext(object_id="10001"))
    assert len(calls["send"]) == 1


# ================ generate_opener 组装口径 ================

def _patch_gen_deps(monkeypatch):
    """替换 generate_opener 的外部依赖(人设/心情/历史),返回记录器"""
    seen = {}

    async def fake_pid(redis, oid):
        return "p1"

    async def fake_get_persona(redis, pid):
        return None                       # 触发默认人设兜底

    async def fake_default(redis):
        return None                       # render(None) 回退 _DEFAULT_PROMPT+契约

    async def fake_inject(redis, oid):
        return {"mood": 0.9, "hint": "\n[当前心情:开心 ^_^,语气轻快]",
                "label": "开心", "kaomoji": "^_^"}

    async def fake_history(redis, oid, *, max_blocks=None, max_messages=None):
        seen["max_messages"] = max_messages
        return [Message(role="user", content="早上好"),
                Message(role="assistant", content="早呀")]

    monkeypatch.setattr(proactive, "get_object_persona_id", fake_pid)
    monkeypatch.setattr(proactive, "get_persona", fake_get_persona)
    monkeypatch.setattr(proactive, "get_default_persona", fake_default)
    monkeypatch.setattr(proactive, "inject_hint", fake_inject)
    monkeypatch.setattr(proactive.chat_store, "get_history", fake_history)
    return seen


class _FakeProvider:
    """记录 messages 并返回固定文本的假 provider"""

    def __init__(self, text='"突然想你了,午饭吃了吗~"'):
        self.text = text
        self.calls: list[list[Message]] = []

    async def chat(self, messages, model="", **opts):
        self.calls.append(messages)

        class _R:
            pass

        r = _R()
        r.text = self.text
        return r


async def test_generate_opener_composition(monkeypatch):
    """组装口径:system=人设渲染+mood hint+OUTPUT_CONTRACT 压轴;携带最近 6 条对话+主动搭话指令"""
    seen = _patch_gen_deps(monkeypatch)
    provider = _FakeProvider()
    monkeypatch.setattr(proactive, "resolve_provider",
                        lambda task, override="": provider)
    text = await generate_opener(None, "10001", "local")
    assert text == "突然想你了,午饭吃了吗~"        # 成对引号被清洗
    assert seen["max_messages"] == 6               # 最近对话条数口径
    msgs = provider.calls[0]
    assert len(msgs) == 4                          # system + 2 历史 + 指令
    system = msgs[0]
    assert system.role == "system"
    assert "[当前心情:开心 ^_^,语气轻快]" in system.content   # mood hint 已注入
    assert system.content.endswith(OUTPUT_CONTRACT)           # 契约压轴(B-2 口径)
    assert msgs[1].role == "user" and msgs[1].content == "早上好"
    assert msgs[2].role == "assistant"
    assert msgs[3].role == "user" and "主动搭话" in msgs[3].content
    assert "AI" in msgs[3].content                 # 指令含禁自称 AI 约束
    assert "编造" in msgs[3].content               # 指令含禁编造约定约束(2026-10-27 事故修复)


async def test_generate_opener_provider_unavailable(monkeypatch):
    """provider 不可用(resolver 返 None):返回空串,不发起调用"""
    _patch_gen_deps(monkeypatch)
    provider = _FakeProvider()
    monkeypatch.setattr(proactive, "resolve_provider", lambda task, override="": None)
    text = await generate_opener(None, "10001", "local")
    assert text == ""
    assert provider.calls == []


# ================ 清洗与 manifest ================

def test_sanitize_opener():
    """去首尾空白/成对引号;空与超长(>120)返回空串"""
    assert _sanitize_opener("  在忙什么呀~ \n") == "在忙什么呀~"
    assert _sanitize_opener('"想你了~"') == "想你了~"
    assert _sanitize_opener("'早呀'") == "早呀"
    assert _sanitize_opener("“晚安”") == "晚安"
    assert _sanitize_opener("") == ""
    assert _sanitize_opener("   ") == ""
    assert _sanitize_opener("字" * 121) == ""
    assert _sanitize_opener("字" * 120) == "字" * 120


def test_as_bool_normalizes_dirty_types():
    """布尔归一:bool 原样;字符串 "false"/None 按 False(防脏类型意外开语音)"""
    assert _as_bool(True) is True and _as_bool(False) is False
    assert _as_bool("false") is False and _as_bool("0") is False
    assert _as_bool("1") is True and _as_bool("true") is True
    assert _as_bool(None) is False


def test_manifest_default_disabled_and_hooks():
    """plugin.yaml 解析:默认关闭(default_enabled=false)+ 声明 on_tick + 门控参数齐备"""
    yaml_path = (Path(__file__).resolve().parents[2] / "app" / "plugins"
                 / "proactive_reply" / "plugin.yaml")
    m = parse_manifest(yaml_path)
    assert m.name == "proactive_reply"
    assert m.default_enabled is False
    assert "on_tick" in m.hook_names
    for key in ("quiet_hours", "daily_max", "min_gap_minutes", "idle_minutes",
                "prob", "use_tts", "llm_provider", "farewell_aware"):
        assert key in m.config_schema, key
