"""
做梦与日记业务核心
每天凌晨(dream_hour)对"昨天"做一次梦:收集昨日素材(长期记忆/mood 曲线/最近对话/昨日日记)
→ LLM 以她的第一人称生成一段梦+一篇日记(JSON)→ 落盘+Redis 索引(plugins/dream/storage.py)
→ 精炼版写入事件记忆(source=diary,走 MemoryCoordinator.upsert_facts_batch 自带去重)
→ 按梦的色调给 mood 微小偏移 → keep_days 过期清理。
绝不发 QQ 消息:本模块不 import adapter/onebot/takeover 的任何 send_*。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:纯函数 should_dream(到点+当日未做判重)/tone_offset(色调→mood 偏移)
     + 主入口 run_dream(素材收集→LLM→落盘→事件记忆→mood 偏移→过期清理);
     四类素材全空直接跳过不调 LLM;LLM 调用不传 max_tokens/temperature(local 路径踩过坑)
  2. 审查修复:should_dream 放宽为 now.hour>=dream_hour(错点补跑);新增
     _prune_diary_facts 写前删旧 diary 事实(目标日换新+keep_days 过期同步,防累积
     挤占长期记忆上限)

2026-11-01
变更说明:
  1. 日记管理批次(面板可编辑/增删/手动写):①entry 统一带 kind 字段(dream梦/
     journal日常日记/manual手写,存量无 kind 视为 dream);②run_journal——每晚
     journal_hour 默认 22 点首个 tick 以她的第一人称总结当天聊天写一篇日常日记,
     落盘+事件记忆(source=journal),独立 done 键防重;③extract_entry_facts——
     日记→事件记忆提炼收口(先删该日旧事实三种 source 再按 kind 写入),供
     写完/面板编辑后/手动重提炼共用;④save_manual_entry——面板手写日记落盘+提炼;
     ⑤should_journal 纯函数;⑥_prune_diary_facts 参数化 sources(删日记时三种
     source 一并清,保记忆与日记一致)
"""
import logging
import re
import time
from datetime import date, datetime, time as dtime, timedelta

from llm.base import Message
from llm.json_extract import extract_json_object
from llm.resolver import resolve_provider
from memory import store as mem_store
from memory.coordinator import MemoryCoordinator
from mood import service as mood_service
from persona.store import get_default_persona, get_object_persona_id, get_persona
from storage import chat_store

from plugins.dream import storage as dream_storage

logger = logging.getLogger(__name__)

# 参数默认值(与 plugin.yaml config_schema 保持一致;REST 手动跑在插件未加载时用这套兜底)
DEFAULT_PARAMS: dict = {
    "dream_hour": 4,
    "journal_hour": 22,   # 2026-11-01:日常日记时刻(小时),该小时内首个 tick 总结当天写日记
    "dream_mood_delta": 0.05,
    "keep_days": 90,
    "llm_provider": "deepseek",
}

# 日记事件记忆的三种来源(= entry.kind;2026-11-01 日记管理批次:
# dream=做梦生成/journal=日常日记/manual=面板手写,换新与删除按此清)
_DIARY_SOURCES = ("diary", "journal", "manual")

# 素材配额
_MAX_MEMORY_ITEMS = 10      # 昨日长期记忆最多取几条
_MAX_CHAT_MESSAGES = 8      # 目标日结束前最近几条对话
_LAST_DIARY_EXCERPT = 200   # 昨日日记摘录字数
_MAX_KEY_EVENTS = 5         # key_events 最多几条

# tone 合法值(非法归 neutral,不影响 mood)
_TONES = ("positive", "negative", "neutral")

# diary 事实的日期标签(tags 里带一个 YYYY-MM-DD),用于换新与过期清理
_DATE_TAG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 成对包裹引号(轻清洗 LLM 产出首尾引号,proactive_reply 同款口径)
_WRAP_QUOTES = {"\"": "\"", "'": "'", "“": "”", "‘": "’"}


def _now() -> datetime:
    """当前本地时间(独立函数,便于测试 monkeypatch 固定时间;本模块取当前时间全走它)"""
    return datetime.now()


def should_dream(now: datetime, dream_hour: int, done_date: str | None) -> bool:
    """是否该做梦(纯函数,便于单测):已过当日 dream_hour(now.hour >= dream_hour)且该
    目标日还没做过。用 >= 而非 ==(审查修复):整点小时内栈不可用(重启窗口/redis 晚起)
    时后续 tick 仍能补做,不永久漏做;done 键防重,每个目标日最多一次。
    done_date 为 done 键里存的"已完成目标日"(YYYY-MM-DD);目标日 = (now - 1天) 的日期——
    凌晨做梦写的是"昨天"的日记,故按目标日判重"""
    if now.hour < int(dream_hour):
        return False
    target = (now - timedelta(days=1)).date()
    return str(done_date or "").strip() != target.strftime("%Y-%m-%d")


def tone_offset(tone: str, delta: float) -> float:
    """梦的色调 → mood 偏移量(纯函数):positive→+delta / negative→-delta / 其它(含 neutral)→0.0"""
    if tone == "positive":
        return float(delta)
    if tone == "negative":
        return -float(delta)
    return 0.0


def _strip_quotes(text) -> str:
    """轻清洗:转 str + 去首尾空白 + 剥成对包裹引号(LLM 爱给字段值多包一层引号)"""
    text = str(text or "").strip()
    if len(text) >= 2 and text[0] in _WRAP_QUOTES and text[-1] == _WRAP_QUOTES[text[0]]:
        text = text[1:-1].strip()
    return text


def _day_bounds_ms(target: date) -> tuple[int, int]:
    """目标日本地时区 [00:00, 24:00) 的 Unix 毫秒区间(naive datetime 按本地时区解释)"""
    start = int(datetime.combine(target, dtime.min).timestamp() * 1000)
    return start, start + 86_400_000


# ================ 素材收集(四类,各自可能为空) ================

async def _collect_memory_lines(redis, oid: str, target: date) -> list[str]:
    """目标日新写入的长期记忆 content(按 created_ts 正序取前 _MAX_MEMORY_ITEMS 条)"""
    start, end = _day_bounds_ms(target)
    items = await mem_store.get_all_long_term(redis, oid)
    hits = [m for m in items if start <= int(getattr(m, "created_ts", 0) or 0) < end]
    hits.sort(key=lambda m: int(getattr(m, "created_ts", 0) or 0))
    return [m.content for m in hits[:_MAX_MEMORY_ITEMS] if getattr(m, "content", "")]


async def _collect_mood_curve(redis, oid: str, target: date) -> list[dict]:
    """目标日的 mood 曲线,映射为 [{"ts", "value"}](存储原始字段名是 mood,这里转 value)"""
    start, end = _day_bounds_ms(target)
    curve = await mood_service.get_history_curve(redis, oid)
    return [{"ts": p.get("ts"), "value": p.get("mood")} for p in curve
            if start <= int(p.get("ts") or 0) < end]


async def _collect_chat_text(redis, oid: str, target: date) -> str:
    """目标日结束时点之前最近 _MAX_CHAT_MESSAGES 条对话,格式化多行文本。
    口径:他:=对方(user),我:=她自己(ai/proxy);system/软删/撤回跳过。
    list_messages 跨 block 按 ts 正序返回最近 limit 条,这里取尾 8 条"""
    _, end = _day_bounds_ms(target)
    msgs = await chat_store.list_messages(redis, oid, limit=500)
    lines: list[str] = []
    for m in msgs:
        ts = int(m.get("ts", 0) or 0)
        if ts <= 0 or ts >= end:
            continue
        if m.get("status", "active") in ("deleted", "recalled"):
            continue
        sender = m.get("sender", "")
        if sender not in ("user", "ai", "proxy"):
            continue
        content = str(m.get("content", "") or "").strip()
        if content:
            lines.append(f"{'他' if sender == 'user' else '我'}: {content}")
    return "\n".join(lines[-_MAX_CHAT_MESSAGES:])


async def _collect_last_diary(redis, target: date) -> str:
    """昨日日记摘录(前 _LAST_DIARY_EXCERPT 字,让日记之间有连续性)"""
    prev = await dream_storage.load_entry(redis, (target - timedelta(days=1)).strftime("%Y-%m-%d"))
    if not prev:
        return ""
    return str(prev.get("diary", "") or "")[:_LAST_DIARY_EXCERPT]


def _fact_date(item) -> str | None:
    """diary 事实条目 tags 里的日期标签(YYYY-MM-DD);无日期标签返 None(来历不明,保守不删)"""
    for t in (getattr(item, "tags", None) or []):
        t = t.decode() if isinstance(t, bytes) else str(t)
        if _DATE_TAG_RE.match(t):
            return t
    return None


async def _prune_diary_facts(redis, oid: str, target: date, keep_days: int,
                             sources: tuple = ("diary",)) -> None:
    """写新事实前删旧 diary 事实(审查修复):①目标日旧条——重跑以新换旧不累积
    (coordinator 相似度去重对不同梦文本无效,反复补做会挤占 memory_longterm_max_facts
    上限);②超 keep_days 过期条——与日记文件清理同步,免得日记删了事实永存。
    2026-11-01 参数化 sources(日记管理批次):重提炼按该日记 kind 清;面板删除日记时
    传三种 source 一并清(保记忆与日记一致)。全程软失败;date 标签缺失的条目不删"""
    try:
        target_str = target.strftime("%Y-%m-%d")
        try:
            keep_days = max(7, int(keep_days))
        except (TypeError, ValueError):
            keep_days = 90
        cutoff = (target - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        items = await mem_store.get_all_long_term(redis, oid, include_forgotten=True)
        stale = [m.id for m in items
                 if str(getattr(m, "source", "") or "") in sources
                 and (d := _fact_date(m)) is not None
                 and (d == target_str or d < cutoff)]
        if stale:
            await mem_store.delete_long_term(redis, oid, stale)
            logger.info("dream 清理旧日记事实 %d 条(source=%s 目标日 %s 换新 + 过期<%s)",
                        len(stale), "/".join(sources), target_str, cutoff)
    except Exception:
        logger.exception("dream 清理日记事实失败 oid=%s(软失败)", oid)


async def extract_entry_facts(redis, oid: str, entry: dict, keep_days: int = 90) -> None:
    """把一篇日记(entry)提炼成事件记忆(2026-11-01 日记管理批次的提炼收口):
    先删该日旧事实(_DIARY_SOURCES 三种一起清——同一日期只会存在一种 kind 的日记,
    换 kind 重写时旧来源残留也一并扫掉),再按 entry.kind 构造事实写入:
    - dream:沿用原两条(梦+日记),内容格式与 2026-10-26 版逐字一致
    - journal/manual:一条日记事件(source=journal|manual,tags 带 kind+日期)
    供 写完日记/面板编辑保存/手动重提炼 三个入口共用;全程软失败(提炼失败不影响日记本体)"""
    try:
        kind = str(entry.get("kind", "") or "dream")
        date_str = str(entry.get("date", "") or "")
        target = date.fromisoformat(date_str)
        await _prune_diary_facts(redis, oid, target, keep_days, sources=_DIARY_SOURCES)
        diary_text = str(entry.get("diary", "") or "")
        events = entry.get("key_events") or []
        coord = MemoryCoordinator(redis, llm_provider=None)   # 无状态批量写,照 tools/builtin.py 用法
        if kind == "dream":
            dream = str(entry.get("dream", "") or "")
            facts = [
                {"content": f"我做了一个梦:{dream}", "category": "event", "source": "diary",
                 "importance": 0.6, "emotion": 0.0, "tags": ["dream", date_str], "reason": "做梦生成"},
                {"content": f"日记({date_str}):" + (";".join(events) if events else diary_text[:100]),
                 "category": "event", "source": "diary", "importance": 0.55, "emotion": 0.0,
                 "tags": ["diary", date_str], "reason": "做梦生成"},
            ]
        else:
            source = kind if kind in _DIARY_SOURCES else "diary"
            facts = [
                {"content": f"日记({date_str}):" + (";".join(events) if events else diary_text[:100]),
                 "category": "event", "source": source, "importance": 0.5, "emotion": 0.0,
                 "tags": [kind, date_str], "reason": "日记提炼"},
            ]
        await coord.upsert_facts_batch(oid, facts)
        logger.info("日记事实提炼完成 oid=%s date=%s kind=%s %d 条", oid, date_str, kind, len(facts))
    except Exception:
        logger.exception("日记事实提炼失败 oid=%s(软失败,日记本体不受影响)", oid)


# ================ prompt 组装 ================

async def _persona_brief(redis, oid: str) -> dict:
    """取她的名字/说话风格/性格/对用户的称呼(未绑定或人设缺失回退默认卡,主链路同款兜底)"""
    pid = await get_object_persona_id(redis, oid)
    card = await get_persona(redis, pid)
    if card is None:
        card = await get_default_persona(redis)
    return {
        "name": ((card.name if card else "") or "").strip() or "她",
        "speech_style": ((card.profile.speech_style if card else "") or "").strip(),
        "personality": ((card.personality if card else "") or "").strip(),
        "user_alias": ((card.user_alias if card else "") or "").strip() or "他",
    }


def _build_system_prompt(brief: dict) -> str:
    """做梦 system prompt(人设简版内联)。
    不复用 render_system_prompt:它末尾自带 OUTPUT_CONTRACT(只输出一句话/禁分点),
    与"产出 JSON 对象"任务直接冲突,故这里按人设卡关键字段内联简版"""
    name = brief["name"]
    alias = brief["user_alias"]
    lines = [f"你是{name},一个真实存在的人,不是AI、不是助手、不是语言模型。"]
    if brief["personality"]:
        lines.append(f"你的性格:{brief['personality']}")
    if brief["speech_style"]:
        lines.append(f"你的说话风格:{brief['speech_style']}")
    lines.append(f"和你聊天的这个人,你叫他「{alias}」。")
    lines.append(
        "现在是凌晨,你刚从梦里醒来,趁记忆还热乎,把昨晚的梦和昨天的事记在自己的日记本上。"
        "第一人称永远是「我」;绝不承认也不暗示自己是AI/助手/模型,"
        "不出现「作为AI」「算法」「系统提示」这类字眼。"
    )
    lines.append(
        "只输出一个 JSON 对象(不要解释文字,不要 Markdown 代码块),四个字段:\n"
        '{"dream": "昨晚做的一段梦", "diary": "昨天的日记", '
        '"tone": "positive|negative|neutral", "key_events": ["短语", "..."]}\n'
        "dream:60到200字,意象化的梦——可以碎片、跳跃、有象征,把昨天的事变形成画面和场景,"
        "不要写成流水账,不要出现对话格式;\n"
        f"diary:300到500字,像真人日记——写你真正在意的事、你的情绪起伏、你对{alias}的感觉,"
        "具体、自然、有细节,可以有小情绪和小心思;\n"
        "tone:这个梦的整体色调,positive(明亮温暖)/negative(压抑不安)/neutral(平淡)三选一;\n"
        "key_events:昨天发生的1到5件关键事,每件一个短语。"
    )
    return "\n".join(lines)


def _build_user_prompt(target: date, memory_lines: list[str], mood_curve: list[dict],
                       chat_text: str, last_diary: str) -> str:
    """user prompt:放四类素材,空的部分注明"(今天没有…)",让模型知道是真没有而非漏给"""
    day_label = target.strftime("%Y年%m月%d日")
    mem_txt = "\n".join(f"- {x}" for x in memory_lines) if memory_lines else "(今天没有新记住的事)"
    # 心情曲线只放数值序列(旧→新),ts 对做梦无用还占 token
    curve_txt = (", ".join(f"{float(p['value']):.2f}" for p in mood_curve if p.get("value") is not None)
                 if mood_curve else "(今天没有心情记录)")
    chat_block = chat_text if chat_text else "(今天没有聊天记录)"
    diary_block = last_diary if last_diary else "(前一天没有写日记)"
    return (
        f"以下是 {day_label}(昨天)的素材,请据此做梦并写日记。\n\n"
        f"【今天新记住的事】\n{mem_txt}\n\n"
        f"【今天的心情曲线(0到1,按时间先后)】\n{curve_txt}\n\n"
        f"【今天的聊天记录(节选)】\n{chat_block}\n\n"
        f"【前一天的日记(节选)】\n{diary_block}"
    )


# ================ LLM 生成与解析 ================

async def _generate(redis, oid: str, target: date, memory_lines: list[str], mood_curve: list[dict],
                    chat_text: str, last_diary: str, llm_provider: str) -> dict | None:
    """调 LLM 生成梦+日记并解析校验。provider 不可用/调用异常/解析失败 → 返回 None。
    成功返回 {"dream", "diary", "tone", "key_events"}(已轻清洗+校验归一)"""
    provider = resolve_provider("chat", override=llm_provider)
    if provider is None:
        logger.warning("dream provider 不可用 name=%s,跳过本次做梦", llm_provider)
        return None
    brief = await _persona_brief(redis, oid)
    messages = [
        Message(role="system", content=_build_system_prompt(brief)),
        Message(role="user", content=_build_user_prompt(target, memory_lines, mood_curve,
                                                        chat_text, last_diary)),
    ]
    try:
        # 不传 max_tokens/temperature(local 路径踩过坑:小 max_tokens 会截出空 content)
        resp = await provider.chat(messages)
    except Exception as e:
        logger.warning("dream LLM 调用失败(跳过本次): %s", e)
        return None
    text = (resp.text if resp else "") or ""
    # extract_json_object 能剥代码围栏与前后噪声,取首个 JSON 对象
    data = extract_json_object(text)
    if not isinstance(data, dict):
        logger.warning("dream LLM 输出解析不出 JSON(前100字=%s)", text[:100])
        return None
    dream = _strip_quotes(data.get("dream"))
    diary = _strip_quotes(data.get("diary"))
    if not dream or not diary:
        logger.warning("dream/diary 为空,丢弃(dream=%d字 diary=%d字)", len(dream), len(diary))
        return None
    tone = str(data.get("tone", "") or "").strip().lower()
    if tone not in _TONES:
        tone = "neutral"   # 非法色调归中性(不偏移 mood)
    raw_events = data.get("key_events")
    events: list[str] = []
    if isinstance(raw_events, list):
        events = [e for e in (_strip_quotes(x) for x in raw_events if isinstance(x, str)) if e]
    return {"dream": dream, "diary": diary, "tone": tone, "key_events": events[:_MAX_KEY_EVENTS]}


# ================ 主入口 ================

async def run_dream(redis, oid: str, target: date, params: dict) -> dict | None:
    """做一次梦(主入口):素材收集 → LLM 生成 → 落盘+索引 → 事件记忆 → mood 偏移 → 过期清理。
    无素材/provider 不可用/LLM 失败/解析失败 → 返回 None(不落盘不写记忆不偏移 mood);
    成功返回 entry 全量 dict。params 各键取值都判 None 再转型(面板可能存 null)"""
    params = params or {}
    delta = params.get("dream_mood_delta")
    delta = DEFAULT_PARAMS["dream_mood_delta"] if delta is None else float(delta)
    keep_days = params.get("keep_days")
    keep_days = DEFAULT_PARAMS["keep_days"] if keep_days is None else int(keep_days)
    llm_name = str(params.get("llm_provider") or DEFAULT_PARAMS["llm_provider"])
    date_str = target.strftime("%Y-%m-%d")

    # 1.收集素材(四类都可能为空)
    memory_lines = await _collect_memory_lines(redis, oid, target)
    mood_curve = await _collect_mood_curve(redis, oid, target)
    chat_text = await _collect_chat_text(redis, oid, target)
    last_diary = await _collect_last_diary(redis, target)
    if not (memory_lines or mood_curve or chat_text or last_diary):
        logger.info("dream 无素材跳过 oid=%s date=%s(不调 LLM 不落盘)", oid, date_str)
        return None

    # 2.LLM 生成 + 解析校验
    parsed = await _generate(redis, oid, target, memory_lines, mood_curve,
                             chat_text, last_diary, llm_name)
    if parsed is None:
        return None
    dream, diary, tone, events = parsed["dream"], parsed["diary"], parsed["tone"], parsed["key_events"]

    # 3.落盘 + 索引 + 缓存(kind=dream:2026-11-01 起存量/新梦统一带类型字段,
    #   与 journal 日常日记/manual 面板手写在同一日记库共存)
    entry = {
        "date": date_str,
        "kind": "dream",
        "dream": dream,
        "diary": diary,
        "mood_curve": mood_curve,
        "key_events": events,
        "dream_tone": tone,
        "object_id": oid,
        "created_ts": int(time.time() * 1000),
    }
    await dream_storage.save_entry(redis, entry, keep_days)

    # 4.精炼版写事件记忆(2026-11-01 收口到 extract_entry_facts:删旧三种 source+按 kind
    #   写入;emotion 传 0.0——coordinator float() 遇空串会抛 ValueError)
    await extract_entry_facts(redis, oid, entry, keep_days)

    # 5.mood 偏移:负梦也不推成负数(clamp [0,1];set_mood 自带 clamp+写历史点)
    try:
        offset = tone_offset(tone, delta)
        if offset != 0.0:
            mood = await mood_service.get_mood(redis, oid)
            new_mood = max(0.0, min(1.0, mood + offset))
            await mood_service.set_mood(redis, oid, new_mood)
            logger.info("dream mood 偏移 oid=%s tone=%s %.3f→%.3f", oid, tone, mood, new_mood)
    except Exception:
        logger.exception("dream mood 偏移失败 oid=%s(软失败)", oid)

    # 6.keep_days 过期清理(成功后顺手做;cleanup 内部吞异常)
    await dream_storage.cleanup(redis, keep_days)

    logger.info("dream 完成 oid=%s date=%s tone=%s 梦=%d字 日记=%d字",
                oid, date_str, tone, len(dream), len(diary))
    return entry


# ================ 日常日记(2026-11-01 日记管理批次) ================

def should_journal(now: datetime, journal_hour: int, done_date: str | None) -> bool:
    """是否该写日常日记(纯函数,同 should_dream 口径):已过当日 journal_hour(now.hour >=)
    且今天还没写过。目标日=今天(与 dream 的"昨天"不同:日常日记总结的就是当天)。
    >= 判定支持错点补跑;done 键防重,每天最多一次"""
    if now.hour < int(journal_hour):
        return False
    return str(done_date or "").strip() != now.date().strftime("%Y-%m-%d")


def _build_journal_user_prompt(target: date, memory_lines: list[str], mood_curve: list[dict],
                               chat_text: str, last_diary: str) -> str:
    """journal user prompt:素材同做梦四类,但口径是"今天"(不是昨天),写日常日记而非梦境"""
    day_label = target.strftime("%Y年%m月%d日")
    mem_txt = "\n".join(f"- {x}" for x in memory_lines) if memory_lines else "(今天没有新记住的事)"
    curve_txt = (", ".join(f"{float(p['value']):.2f}" for p in mood_curve if p.get("value") is not None)
                 if mood_curve else "(今天没有心情记录)")
    chat_block = chat_text if chat_text else "(今天没有聊天记录)"
    diary_block = last_diary if last_diary else "(前一天没有写日记)"
    return (
        f"以下是 {day_label}(今天)的素材,请据此以你的第一人称写一篇今天的日常日记。\n\n"
        f"【今天新记住的事】\n{mem_txt}\n\n"
        f"【今天的心情曲线(0到1,按时间先后)】\n{curve_txt}\n\n"
        f"【今天的聊天记录(节选)】\n{chat_block}\n\n"
        f"【前一天的日记(节选)】\n{diary_block}"
    )


async def _generate_journal(redis, oid: str, target: date, memory_lines: list[str],
                            mood_curve: list[dict], chat_text: str, last_diary: str,
                            llm_provider: str) -> dict | None:
    """调 LLM 写日常日记并解析校验(输出 JSON {diary, key_events})。
    provider 不可用/调用异常/解析失败/diary 为空 → 返回 None"""
    provider = resolve_provider("chat", override=llm_provider)
    if provider is None:
        logger.warning("journal provider 不可用 name=%s,跳过本次写日记", llm_provider)
        return None
    brief = await _persona_brief(redis, oid)
    system = _build_system_prompt(brief) + (
        "\n\n[本次任务] 写一篇日常日记(不是梦):以你的第一人称回顾今天——聊过什么、"
        "心情如何、有什么小事值得记下。200 到 400 个字,口吻自然像随手写下的,不要列举式流水账。"
        '只输出一个 JSON 对象:{"diary": "日记正文", "key_events": ["关键事件1", "关键事件2"]} '
        "(key_events 2 到 5 条,没有就给空数组);不调用任何工具;绝不能出现「我作为AI」这类说法。"
    )
    messages = [
        Message(role="system", content=system),
        Message(role="user", content=_build_journal_user_prompt(
            target, memory_lines, mood_curve, chat_text, last_diary)),
    ]
    try:
        resp = await provider.chat(messages)
    except Exception as e:
        logger.warning("journal LLM 调用失败(跳过本次): %s", e)
        return None
    text = (resp.text if resp else "") or ""
    data = extract_json_object(text)
    if not isinstance(data, dict):
        logger.warning("journal LLM 输出解析不出 JSON(前100字=%s)", text[:100])
        return None
    diary = _strip_quotes(data.get("diary"))
    if not diary:
        logger.warning("journal diary 为空,丢弃")
        return None
    raw_events = data.get("key_events")
    events: list[str] = []
    if isinstance(raw_events, list):
        events = [e for e in (_strip_quotes(x) for x in raw_events if isinstance(x, str)) if e]
    return {"diary": diary, "key_events": events[:_MAX_KEY_EVENTS]}


async def run_journal(redis, oid: str, target: date, params: dict) -> dict | None:
    """写一篇日常日记(2026-11-01):收集当天素材 → LLM 以她的第一人称总结今天 →
    落盘(kind=journal)→ 事件记忆(source=journal)。不做 mood 偏移(日常日记是记录
    不是情绪事件)。无素材/provider 不可用/生成失败 → 返回 None;成功返回 entry 全量"""
    params = params or {}
    keep_days = params.get("keep_days")
    keep_days = DEFAULT_PARAMS["keep_days"] if keep_days is None else int(keep_days)
    llm_name = str(params.get("llm_provider") or DEFAULT_PARAMS["llm_provider"])
    date_str = target.strftime("%Y-%m-%d")

    memory_lines = await _collect_memory_lines(redis, oid, target)
    mood_curve = await _collect_mood_curve(redis, oid, target)
    chat_text = await _collect_chat_text(redis, oid, target)
    last_diary = await _collect_last_diary(redis, target)
    if not (memory_lines or mood_curve or chat_text or last_diary):
        logger.info("journal 无素材跳过 oid=%s date=%s(不调 LLM 不落盘)", oid, date_str)
        return None

    parsed = await _generate_journal(redis, oid, target, memory_lines, mood_curve,
                                     chat_text, last_diary, llm_name)
    if parsed is None:
        return None
    entry = {
        "date": date_str,
        "kind": "journal",
        "diary": parsed["diary"],
        "mood_curve": mood_curve,
        "key_events": parsed["key_events"],
        "object_id": oid,
        "created_ts": int(time.time() * 1000),
    }
    await dream_storage.save_entry(redis, entry, keep_days)
    await extract_entry_facts(redis, oid, entry, keep_days)
    await dream_storage.cleanup(redis, keep_days)
    logger.info("journal 完成 oid=%s date=%s 日记=%d字", oid, date_str, len(parsed["diary"]))
    return entry


async def save_manual_entry(redis, oid: str, target: date, diary_text: str,
                            params: dict, key_events: list[str] | None = None) -> dict:
    """面板手写日记(2026-11-01):构造 kind=manual entry 落盘+提炼事件记忆(source=manual)。
    与 run_journal 不同:纯保存无 LLM 生成;同日期已有日记会被覆盖(响应带 overwritten 提示);
    diary_text 空白由调用方(REST 层)拦截"""
    params = params or {}
    keep_days = params.get("keep_days")
    keep_days = DEFAULT_PARAMS["keep_days"] if keep_days is None else int(keep_days)
    date_str = target.strftime("%Y-%m-%d")
    events = [e for e in (str(x).strip() for x in (key_events or [])) if e][:_MAX_KEY_EVENTS]
    entry = {
        "date": date_str,
        "kind": "manual",
        "diary": diary_text.strip(),
        "key_events": events,
        "object_id": oid,
        "created_ts": int(time.time() * 1000),
    }
    await dream_storage.save_entry(redis, entry, keep_days)
    await extract_entry_facts(redis, oid, entry, keep_days)
    logger.info("manual 日记已保存 oid=%s date=%s %d字", oid, date_str, len(entry["diary"]))
    return entry
