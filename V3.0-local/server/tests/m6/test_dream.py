"""
dream 插件单测(做梦与日记)
覆盖:should_dream/tone_offset 纯函数边界;on_tick 门控(命中一次/非命中小时/空素材仍置 done 键);
run_dream 全链(素材全空跳过、LLM 三种失败路径、成功路径落盘+索引+缓存+事件记忆+mood 偏移+prompt 口径、
重复跑事件记忆去重、mood clamp 边界、tone 非法归 neutral+key_events 过滤截断);
storage(save_entry 非法日期守卫、load_entry 缓存 miss 文件命中、list_dates clamp、cleanup 三清+孤儿文件);
plugin.yaml manifest 校验。凡会落盘的测试都把 DIARY_DIR monkeypatch 到 tmp_path(不碰真实 data/diary);
凡会走到 _generate 的测试都先种 persona 绑定(避开 get_default_persona 的真实文件双写)。

日期: 2026-10-26

2026-10-26
变更说明：
  1. 新增 dream 插件测试(纯函数 + on_tick 门控 + run_dream 全链 + storage + manifest)

2026-10-27
变更说明：
  1. low 项修复配套:原子写失败清 .tmp、cleanup 兜底扫 *.json.tmp 残骸 两测
"""
import json
from datetime import date, datetime
from pathlib import Path

import pytest

import plugins.dream.plugin as dp
import plugins.dream.service as svc
import plugins.dream.storage as dream_storage
from llm.base import LLMResponse, Message
from memory import store as mem_store
from memory.models import Category, MemoryItem
from mood import service as mood_service
from pipeline.context import MessageContext
from plugins.base import HookResult, PluginContext
from plugins.dream.plugin import DreamPlugin
from plugins.manifest import PluginManifest, parse_manifest
from storage import chat_store

# 测试基准:固定"现在"=2026-10-26 04:10(dream_hour 当小时内),目标日("昨天")=2026-10-25
_OID = "10001"
_TARGET = date(2026, 10, 25)
_NOW = datetime(2026, 10, 26, 4, 10)
# 全链基准参数(与 plugin.yaml 默认一致)
_PARAMS = {"dream_hour": 4, "dream_mood_delta": 0.05, "keep_days": 90, "llm_provider": "deepseek"}


class _FakeManager:
    """轻量 mock:get_params 返回构造时指定的参数(不走 config_schema 合并,测试显式给全)"""

    def __init__(self, params=None):
        self._params = params or {}

    async def get_params(self, name, oid):
        return dict(self._params)


def _make_plugin(params=None, redis=None):
    """构造插件实例(m6 惯例:手写 pctx 注入,不经 PluginManager)"""
    p = DreamPlugin()
    p.manifest = PluginManifest(name="dream")
    p.pctx = PluginContext(manager=_FakeManager(params), redis=redis,
                           settings=None, manifest=p.manifest)
    return p


def _llm_text(tone: str = "positive", events: list | None = None) -> str:
    """构造 LLM 假输出:带 Markdown 代码围栏与前后噪声(测 extract_json_object 剥围栏路径)"""
    payload = {
        "dream": "梦见一片会发光的海,他站在浪里朝我招手",
        "diary": "今天他夸我记性好,晚上一起看了新番,开心了一整天。",
        "tone": tone,
        "key_events": events if events is not None else ["事件一"],
    }
    return "嗯,记下来了:\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```\n以上。"


class _FakeProvider:
    """记录 chat 调用并返回构造时指定文本的假 provider(raise_exc 注入调用异常路径)"""

    def __init__(self, text: str = "", raise_exc: Exception | None = None):
        self.text = text
        self.raise_exc = raise_exc
        self.calls: list[list[Message]] = []

    async def chat(self, messages, model="", **opts):
        self.calls.append(messages)
        if self.raise_exc:
            raise self.raise_exc
        return LLMResponse(text=self.text)


def _patch_llm(monkeypatch, provider):
    """把 service 命名空间的 resolve_provider 换成返回假 provider(module 唯一实例上的 patch)"""
    monkeypatch.setattr(svc, "resolve_provider", lambda task, override="": provider)


async def _seed_persona(fake_redis):
    """种人设+对象绑定:让 _persona_brief 走真实 get_persona 路径,
    避开 get_default_persona 兜底的真实文件双写;bind 键优先于全局默认,零 settings 依赖"""
    from persona.models import PersonaCard
    card = PersonaCard(id="p_dream", name="角色", personality="温柔慵懒", user_alias="主人")
    card.profile.speech_style = "温柔慵懒爱用叠词"
    await fake_redis.set("mychat:persona:p_dream", json.dumps(card.to_dict(), ensure_ascii=False))
    await fake_redis.set(f"mychat:obj:{_OID}:persona", "p_dream")


def _entry(d: str, diary: str = "今天他突然夸我记性好,有点开心。", tone: str = "positive") -> dict:
    """构造一条最小完整 entry(storage 测试用;date 合法即可保存)"""
    return {"date": d, "dream": "梦见发光的海", "diary": diary, "mood_curve": [],
            "key_events": ["被夸"], "dream_tone": tone, "object_id": _OID,
            "created_ts": 1798000000000}


async def _seed_material(fake_redis, *, memory=True, mood_curve=True, chat=True,
                         prev_diary=True, mood=None):
    """种目标日四类素材(各可关,全关=素材全空场景);mood 直写键避免引入 time.time() 历史点"""
    start, _end = svc._day_bounds_ms(_TARGET)   # 目标日 [00:00,24:00) 毫秒区间(与被测代码同口径)
    if memory:
        await mem_store.upsert_long_term(fake_redis, _OID, MemoryItem(
            id="m1", content="主人夸我记性好", category=Category.EVENT,
            importance=0.7, created_ts=start + 3600_000))
    if mood_curve:
        for ts, val in ((start + 2 * 3600_000, 0.4), (start + 5 * 3600_000, 0.6)):
            await fake_redis.lpush(f"mychat:mood:{_OID}:history",
                                   json.dumps({"ts": ts, "mood": val}))
    if chat:
        await chat_store.append_message(fake_redis, _OID, sender="user", content="今天的新番好看吗",
                                        ts=start + 3 * 3600_000)
        await chat_store.append_message(fake_redis, _OID, sender="ai", content="好看,一起看",
                                        ts=start + 4 * 3600_000)
    if prev_diary:
        await dream_storage.save_entry(fake_redis, _entry("2026-10-24", diary="昨天写了点东西,心情平静。"),
                                       keep_days=90)
    if mood is not None:
        await fake_redis.set(f"mychat:mood:{_OID}", str(mood))


# ================ 纯函数:should_dream / tone_offset ================

def test_should_dream_boundaries():
    """到点/已过点补跑/未到点/同目标日已 done/别的日 done/dream_hour 0 与 23 边界"""
    now = datetime(2026, 10, 26, 4, 30)                       # 目标日 = 2026-10-25
    assert svc.should_dream(now, 4, None) is True             # 到点且未做
    assert svc.should_dream(now, 4, "2026-10-25") is False    # 同目标日已 done
    assert svc.should_dream(now, 4, "2026-10-24") is True     # done 的是别的目标日
    assert svc.should_dream(now, 4, "") is True               # done 键空串视为未做
    assert svc.should_dream(now, 5, None) is False            # 未到点(4:30 < 5)
    assert svc.should_dream(datetime(2026, 10, 26, 5, 30), 4, None) is True    # 错过整点补跑(>=)
    assert svc.should_dream(datetime(2026, 10, 26, 0, 5), 0, None) is True     # 0 点边界
    assert svc.should_dream(datetime(2026, 10, 26, 23, 59), 23, None) is True  # 23 点边界
    assert svc.should_dream(datetime(2026, 10, 26, 23, 59), 22, None) is True  # 过点同样补跑


def test_tone_offset():
    """色调→mood 偏移:positive 正/negative 负/neutral 与非法色调 0"""
    assert svc.tone_offset("positive", 0.05) == 0.05
    assert svc.tone_offset("negative", 0.05) == -0.05
    assert svc.tone_offset("neutral", 0.05) == 0.0
    assert svc.tone_offset("happy", 0.05) == 0.0


# ================ on_tick 门控 ================

async def test_on_tick_fires_once_per_day(fake_redis, tmp_path, monkeypatch):
    """命中小时连打两次 tick:LLM 只烧一次(第二次被 done 键拦下),done 键值=目标日串"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    monkeypatch.setattr(svc, "_now", lambda: _NOW)
    provider = _FakeProvider(_llm_text("positive", ["他夸我记性好", "一起看了新番"]))
    _patch_llm(monkeypatch, provider)
    await _seed_persona(fake_redis)
    await _seed_material(fake_redis)
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    assert await p.on_tick(MessageContext(object_id=_OID)) is HookResult.CONTINUE
    assert await p.on_tick(MessageContext(object_id=_OID)) is HookResult.CONTINUE
    assert len(provider.calls) == 1                    # 一天只真正尝试一次
    done_key = dp._DONE_KEY.format(oid=_OID, yyyymmdd="20261025")
    assert await fake_redis.get(done_key) == "2026-10-25"
    assert await fake_redis.ttl(done_key) > 0          # TTL 3 天防重试烧 LLM
    assert (tmp_path / "2026-10-25.json").is_file()    # 首次已产出日记


async def test_on_tick_off_hour_noop(fake_redis, tmp_path, monkeypatch):
    """未到 dream_hour(5 点 < 6):不调 LLM、不落盘、不置 done 键(过点会补跑,见 boundaires)"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    monkeypatch.setattr(svc, "_now", lambda: datetime(2026, 10, 26, 5, 0))
    provider = _FakeProvider(_llm_text())
    _patch_llm(monkeypatch, provider)
    params = dict(_PARAMS, dream_hour=6)   # 当前 5 点还没到 6 点
    p = _make_plugin(params, redis=fake_redis)
    assert await p.on_tick(MessageContext(object_id=_OID)) is HookResult.CONTINUE
    assert provider.calls == []
    assert await fake_redis.get(dp._DONE_KEY.format(oid=_OID, yyyymmdd="20261025")) is None
    assert not list(tmp_path.iterdir())


async def test_on_tick_no_material_still_marks_done(fake_redis, tmp_path, monkeypatch):
    """无素材:不调 LLM 不落盘,但 done 键照置(防同小时内每分钟重试烧 LLM)"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    monkeypatch.setattr(svc, "_now", lambda: _NOW)
    provider = _FakeProvider(_llm_text())
    _patch_llm(monkeypatch, provider)
    p = _make_plugin(dict(_PARAMS), redis=fake_redis)
    assert await p.on_tick(MessageContext(object_id=_OID)) is HookResult.CONTINUE
    assert provider.calls == []
    assert not list(tmp_path.iterdir())
    assert await fake_redis.get(dp._DONE_KEY.format(oid=_OID, yyyymmdd="20261025")) == "2026-10-25"


# ================ run_dream ================

async def test_run_dream_empty_material_skips(fake_redis, tmp_path, monkeypatch):
    """四类素材全空:返 None,不调 LLM、不落盘、不写记忆、不动 mood"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    provider = _FakeProvider(_llm_text())
    _patch_llm(monkeypatch, provider)
    assert await svc.run_dream(fake_redis, _OID, _TARGET, dict(_PARAMS)) is None
    assert provider.calls == []
    assert not list(tmp_path.iterdir())
    assert await fake_redis.hgetall(f"mychat:mem:{_OID}:long") == {}
    assert await fake_redis.get(f"mychat:mood:{_OID}") is None


@pytest.mark.parametrize("mode", ["empty_text", "raise", "not_json"])
async def test_run_dream_llm_failures(fake_redis, tmp_path, monkeypatch, mode):
    """LLM 失败三路径(空文本/调用抛异常/输出非 JSON):返 None 且不落盘不缓存"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    await _seed_persona(fake_redis)
    await _seed_material(fake_redis, mood_curve=False, chat=False, prev_diary=False)  # 只种长期记忆
    if mode == "raise":
        provider = _FakeProvider(raise_exc=RuntimeError("llm down"))
    elif mode == "not_json":
        provider = _FakeProvider("这不是 JSON,只是闲聊")
    else:
        provider = _FakeProvider("")
    _patch_llm(monkeypatch, provider)
    assert await svc.run_dream(fake_redis, _OID, _TARGET, dict(_PARAMS)) is None
    assert len(provider.calls) == 1                    # 素材非空,LLM 确实被调过一次
    assert not list(tmp_path.iterdir())
    assert await fake_redis.get("mychat:diary:2026-10-25") is None


async def test_run_dream_success_full_chain(fake_redis, tmp_path, monkeypatch):
    """成功路径:素材→LLM(剥代码围栏)→entry 全字段→落盘+索引+缓存→事件记忆→mood 偏移→prompt 口径"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    await _seed_persona(fake_redis)
    await _seed_material(fake_redis, mood=0.5)
    start, _end = svc._day_bounds_ms(_TARGET)
    provider = _FakeProvider(_llm_text("positive", ["他夸我记性好", "一起看了新番"]))
    _patch_llm(monkeypatch, provider)
    entry = await svc.run_dream(fake_redis, _OID, _TARGET, dict(_PARAMS))
    assert entry is not None
    # 1)entry 字段齐全且值与 LLM 产出一致(围栏与噪声已剥净)
    assert entry["date"] == "2026-10-25" and entry["object_id"] == _OID
    assert entry["dream"] == "梦见一片会发光的海,他站在浪里朝我招手"
    assert entry["diary"] == "今天他夸我记性好,晚上一起看了新番,开心了一整天。"
    assert entry["dream_tone"] == "positive"
    assert entry["key_events"] == ["他夸我记性好", "一起看了新番"]
    assert entry["created_ts"] > 0
    assert all(set(p) == {"ts", "value"} for p in entry["mood_curve"])
    assert {p["ts"]: p["value"] for p in entry["mood_curve"]} == {
        start + 2 * 3600_000: 0.4, start + 5 * 3600_000: 0.6}
    # 2)落盘 + ZSET 索引(score=YYYYMMDD 整数)+ 缓存键
    assert (tmp_path / "2026-10-25.json").is_file()
    assert json.loads((tmp_path / "2026-10-25.json").read_text(encoding="utf-8")) == entry
    assert await fake_redis.zscore("mychat:diary:index", "2026-10-25") == 20261025
    assert await fake_redis.get("mychat:diary:2026-10-25") is not None
    # 3)事件记忆:两条 source=diary 的 event 条目(梦/日记各一)
    items = [json.loads(v) for v in (await fake_redis.hgetall(f"mychat:mem:{_OID}:long")).values()]
    diary_items = [m for m in items if m.get("source") == "diary"]
    assert len(diary_items) == 2
    assert all(m["category"] == "event" for m in diary_items)
    assert any(m["content"].startswith("我做了一个梦:") and "发光的海" in m["content"]
               for m in diary_items)
    assert any(m["content"].startswith("日记(2026-10-25):") for m in diary_items)
    # 4)mood 按色调偏移:0.5 + 0.05 = 0.55
    assert await mood_service.get_mood(fake_redis, _OID) == 0.55
    # 5)prompt 组装:人设名进 system;"他:/我:"对话、记忆、曲线数值序列、昨日日记摘录进 user
    msgs = provider.calls[0]
    assert msgs[0].role == "system" and "角色" in msgs[0].content
    user = msgs[1].content
    assert "他: 今天的新番好看吗" in user and "我: 好看,一起看" in user
    assert "主人夸我记性好" in user          # 目标日长期记忆
    assert "0.40, 0.60" in user             # mood 曲线旧→新数值序列
    assert "昨天写了点东西" in user          # 昨日日记摘录


async def test_run_dream_repeat_no_duplicate_memory(fake_redis, tmp_path, monkeypatch):
    """重复补跑:日记文件覆盖不堆积;事件记忆以新换旧(审查修复:写前 _prune_diary_facts
    删目标日旧条再写,不同梦文本也绝不累积,免挤占长期记忆上限)"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    await _seed_persona(fake_redis)
    await _seed_material(fake_redis)
    provider = _FakeProvider(_llm_text("neutral"))
    _patch_llm(monkeypatch, provider)
    for _ in range(2):
        assert await svc.run_dream(fake_redis, _OID, _TARGET, dict(_PARAMS)) is not None
    items = [json.loads(v) for v in (await fake_redis.hgetall(f"mychat:mem:{_OID}:long")).values()]
    diary_items = [m for m in items if m.get("source") == "diary"]
    assert len(diary_items) == 2                              # 仍是两条(换新而非堆积)
    assert len(list(tmp_path.glob("2026-10-25*"))) == 1       # 文件覆盖写,不堆重复


async def test_prune_diary_facts_expiry_and_refresh(fake_redis, monkeypatch):
    """_prune_diary_facts 两类清理:目标日旧条换新 + 超 keep_days 过期条删除;
    无日期标签的 diary 条与其它来源条不删"""
    await _seed_persona(fake_redis)
    today = date(2026, 10, 26)
    # 三条旧 diary 事实:目标日换新对象 / 过期(1900-01-01 < cutoff) / 无日期标签(保守保留)
    keep = [
        {"content": "目标日旧梦", "category": "event", "source": "diary",
         "tags": ["dream", "2026-10-25"]},
        {"content": "远古日记", "category": "event", "source": "diary",
         "tags": ["diary", "1900-01-01"]},
        {"content": "无日期标签", "category": "event", "source": "diary",
         "tags": ["diary"]},
        {"content": "普通记忆不删", "category": "event", "source": "chat",
         "tags": ["2026-10-25"]},
    ]
    for i, f in enumerate(keep):
        await mem_store.upsert_long_term(fake_redis, _OID, MemoryItem(
            id=f"mem_prune_{i}", content=f["content"], category=Category(f["category"]),
            source=f["source"], tags=list(f["tags"]),
        ))
    items = await mem_store.get_all_long_term(fake_redis, _OID, include_forgotten=True)
    assert len(items) == 4
    await svc._prune_diary_facts(fake_redis, _OID, date(2026, 10, 25), 90)   # target=10-25,keep=90
    items = await mem_store.get_all_long_term(fake_redis, _OID, include_forgotten=True)
    contents = {m.content for m in items}
    assert contents == {"无日期标签", "普通记忆不删"}   # 换新条+过期条已删


@pytest.mark.parametrize("tone,initial,expected", [
    ("negative", 0.02, 0.0),    # 负梦不推成负数(clamp 下界 0)
    ("positive", 0.98, 1.0),    # 正梦不超 1(clamp 上界 1)
    ("neutral", 0.5, 0.5),      # 中性不动
])
async def test_run_dream_mood_clamp(fake_redis, tmp_path, monkeypatch, tone, initial, expected):
    """mood 偏移边界:tone×初值→期望值(delta=0.05)"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    await _seed_persona(fake_redis)
    await _seed_material(fake_redis, mood_curve=False, chat=False, prev_diary=False, mood=initial)
    _patch_llm(monkeypatch, _FakeProvider(_llm_text(tone)))
    assert await svc.run_dream(fake_redis, _OID, _TARGET, dict(_PARAMS)) is not None
    assert await mood_service.get_mood(fake_redis, _OID) == expected


async def test_run_dream_invalid_tone_and_events_normalized(fake_redis, tmp_path, monkeypatch):
    """tone 非法(happy)归 neutral 且不偏移 mood;key_events 混空串/非串被滤、超 5 条截断"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    await _seed_persona(fake_redis)
    await _seed_material(fake_redis, mood_curve=False, chat=False, prev_diary=False, mood=0.5)
    events = ["", "  ", 5, "事件一", "事件二", "事件三", "事件四", "事件五", "事件六"]
    _patch_llm(monkeypatch, _FakeProvider(_llm_text("happy", events)))
    entry = await svc.run_dream(fake_redis, _OID, _TARGET, dict(_PARAMS))
    assert entry["dream_tone"] == "neutral"
    assert entry["key_events"] == ["事件一", "事件二", "事件三", "事件四", "事件五"]  # 滤空+去非串+截 5
    assert await mood_service.get_mood(fake_redis, _OID) == 0.5   # 中性不偏移


# ================ storage ================

async def test_storage_cleanup(fake_redis, tmp_path, monkeypatch):
    """cleanup(today 注入):过期三处全清(文件+索引+缓存)、索引失联孤儿文件按文件名清、其余保留"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    for d in ("2026-10-15", "2026-10-16", "2026-10-17"):
        await dream_storage.save_entry(fake_redis, _entry(d), keep_days=90)
    (tmp_path / "2026-10-01.json").write_text("{}", encoding="utf-8")   # 索引失联的过期孤儿文件
    await dream_storage.cleanup(fake_redis, keep_days=10, today=date(2026, 10, 26))
    # cutoff=2026-10-16:严格早于 cutoff 的三处全清
    assert not (tmp_path / "2026-10-15.json").exists()
    assert not (tmp_path / "2026-10-01.json").exists()
    assert await fake_redis.zscore("mychat:diary:index", "2026-10-15") is None
    assert await fake_redis.get("mychat:diary:2026-10-15") is None
    # cutoff 当天与新于 cutoff 的全保留
    assert (tmp_path / "2026-10-16.json").exists() and (tmp_path / "2026-10-17.json").exists()
    assert await fake_redis.zscore("mychat:diary:index", "2026-10-16") == 20261016
    assert await fake_redis.get("mychat:diary:2026-10-16") is not None
    assert await dream_storage.list_dates(fake_redis) == ["2026-10-17", "2026-10-16"]


async def test_write_json_atomic_failure_removes_tmp(tmp_path, monkeypatch):
    """原子写中途抛错(如磁盘满):.tmp 即删不留残骸,原文件不受影响(low 项修复)"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    target = tmp_path / "2026-10-25.json"
    dream_storage._write_json_atomic(target, {"date": "2026-10-25"})   # 先正常落一份
    def _boom(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(dream_storage.json, "dump", _boom)             # 模拟写一半炸
    with pytest.raises(OSError):
        dream_storage._write_json_atomic(target, {"date": "2026-10-25", "x": 1})
    assert not (tmp_path / "2026-10-25.json.tmp").exists()             # 残骸已清
    assert json.loads(target.read_text(encoding="utf-8"))["date"] == "2026-10-25"  # 原文件未损


async def test_cleanup_sweeps_tmp_leftovers(fake_redis, tmp_path, monkeypatch):
    """cleanup 兜底扫 *.json.tmp 残骸(进程被杀遗留的半截文件):无日期语义一律删,正常文件不动"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    (tmp_path / "2026-10-20.json.tmp").write_text("{half", encoding="utf-8")   # 被杀残骸
    (tmp_path / "2026-10-21.json").write_text("{}", encoding="utf-8")          # 未过期正常文件
    await dream_storage.cleanup(fake_redis, keep_days=90, today=date(2026, 10, 26))
    assert not list(tmp_path.glob("*.json.tmp"))
    assert (tmp_path / "2026-10-21.json").exists()


async def test_load_entry_paths_and_list_dates_clamp(fake_redis, tmp_path, monkeypatch):
    """save_entry 非法日期守卫;load_entry 缓存命中/缓存 miss 文件命中/双 miss None;list_dates clamp"""
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    await dream_storage.save_entry(fake_redis, _entry("bad-date"), keep_days=90)   # 非法日期被守卫拦下
    assert await fake_redis.zcard("mychat:diary:index") == 0
    assert not list(tmp_path.iterdir())
    await dream_storage.save_entry(fake_redis, _entry("2026-10-25"), keep_days=90)
    assert (await dream_storage.load_entry(fake_redis, "2026-10-25"))["date"] == "2026-10-25"  # 缓存命中
    await fake_redis.delete("mychat:diary:2026-10-25")
    assert (await dream_storage.load_entry(fake_redis, "2026-10-25"))["date"] == "2026-10-25"  # 文件命中
    assert await dream_storage.load_entry(fake_redis, "2026-01-01") is None                    # 双 miss
    # limit clamp:0/负 → 1(只回最新一条);>365 → 365(直接种 400 成员验证封顶)
    await fake_redis.zadd("mychat:diary:index", {f"2026-10-{i:02d}": 20261000 + i for i in range(1, 25)})
    assert await dream_storage.list_dates(fake_redis, limit=0) == ["2026-10-25"]
    assert await dream_storage.list_dates(fake_redis, limit=-5) == ["2026-10-25"]
    await fake_redis.zadd("mychat:diary:index", {f"m{i}": i for i in range(400)})
    assert len(await dream_storage.list_dates(fake_redis, limit=9999)) == 365


# ================ manifest ================

def test_manifest_default_disabled_and_hooks():
    """plugin.yaml:默认关闭 + on_tick(130)+ 四参数齐备,且默认值与代码 DEFAULT_PARAMS 一致"""
    yaml_path = (Path(__file__).resolve().parents[2] / "app" / "plugins" / "dream" / "plugin.yaml")
    m = parse_manifest(yaml_path)
    assert m.name == "dream"
    assert m.default_enabled is False
    assert m.hook_names == ["on_tick"]
    assert m.hooks[0].priority == 130
    defaults = {k: v["default"] for k, v in m.config_schema.items()}
    assert defaults == {"dream_hour": 4, "dream_mood_delta": 0.05,
                        "keep_days": 90, "llm_provider": "deepseek"}
    assert defaults == svc.DEFAULT_PARAMS
