"""
proactive_reply 插件(主动消息·主动搭话)
- on_tick:对当前对象做五重门控(静默时段/每日上限/最小间隔/空闲阈值/概率),全过才主动搭话;
  命中后复用主链路口径(人设 render_system_prompt + mood hint + OUTPUT_CONTRACT + 最近 6 条对话)
  让本地模型生成一句 20-60 字开场白,经 takeover.send_proactive 以人设身份发出
  (落 proxy 消息进 live 历史 + 下发 QQ,面板可见)。
- 状态存 Redis(mychat:proactive:*):上次发送时间戳 + 当日计数(按日期分键,自然日切换自动归零)。
- 全链软失败:任何异常只记日志绝不外抛,不影响 tick 循环与其他插件。

日期: 2026-10-25

2026-10-25
变更说明:
  1. 新增 proactive_reply 插件:五重门控 + 本地模型开场白生成 + takeover 下发(默认关闭)
  2. 对抗审查修正:系统级静默(AI 静默模式/手动静默窗)优先于一切门控;下发异常仍记账
     (防无界重试);参数脏类型 fail-closed;指令注入当前时辰;use_tts 宽容归一

2026-10-27
变更说明:
  1. 晚安事故修复(双栈同步):①晚安感知门控——对方末条消息为道别/就寝语时静默直到
     其再开口(此前 01:59 道晚安后 09:30 静默段一结束就补发"早上好"被投诉扰人);
  2. 开场白指令加禁编造约束(此前凭空编"说好早点睡的""说好要啃高数"被用户三轮对质)。
     两改动同步镜像到 Vdafeiyu 同路径文件(保持逐字节一致)。
"""
import logging
import random
from datetime import datetime

from llm.base import Message
from llm.resolver import resolve_provider
from mood.service import inject_hint
from persona.renderer import OUTPUT_CONTRACT, render_system_prompt
from persona.store import get_default_persona, get_object_persona_id, get_persona
from plugins.base import Plugin, HookResult
from plugins.time_aware.plugin import season_label, time_of_day   # 复用时辰/季节纯函数
from storage import chat_store, takeover_store
from takeover.service import send_proactive

logger = logging.getLogger(__name__)

# 状态键:上次主动发送时间戳(unix 秒)/当日发送计数(按 yyyymmdd 分键,跨日自动从零计)
_LAST_KEY = "mychat:proactive:last:{oid}"
_COUNT_KEY = "mychat:proactive:count:{oid}:{day}"
_COUNT_TTL = 2 * 86400    # 计数键 2 天过期:跨日后的旧键自然清理
_LAST_TTL = 7 * 86400     # 时间戳键 7 天过期:久未主动的对象自动清状态
CONTEXT_MESSAGES = 6      # 生成开场白携带的最近对话条数(旧→新,时间正序)
_MAX_OPENER_LEN = 120     # 开场白长度安全上限(超出视为模型跑飞,整条丢弃)
_WRAP_QUOTES = {"\"": "\"", "'": "'", "“": "”", "‘": "’"}   # 包裹引号对(开→闭,含全角成对)
# 道别/就寝词(2026-10-27 晚安事故加):命中即视为"对方已道别",主动搭话静默直到其再开口。
# 宁可误判少发(防扰民同向),不追词表完备——"不睡了"这类反说也会命中,方向上可接受
_FAREWELL_WORDS = ("晚安", "睡了", "睡觉", "先睡", "去睡", "困了", "好梦", "休息了", "去休息")


def _now() -> datetime:
    """当前本地时间(独立函数,便于测试 monkeypatch 固定时间)"""
    return datetime.now()


def parse_quiet_hours(text: str) -> tuple[int, int] | None:
    """解析静默时段 "HH:MM-HH:MM" 为 (起,止) 当日分钟数;支持跨零点(如 23:30-08:00,起>止)。
    非法输入返回 None(调用方按防扰民原则直接不发送)。"""
    try:
        raw_start, raw_end = str(text).strip().split("-")
        sh, sm = (int(x) for x in raw_start.strip().split(":"))
        eh, em = (int(x) for x in raw_end.strip().split(":"))
        if not (0 <= sh < 24 and 0 <= eh < 24 and 0 <= sm < 60 and 0 <= em < 60):
            return None
        return sh * 60 + sm, eh * 60 + em
    except Exception:
        return None


def in_quiet_hours(now: datetime, q_start: int, q_end: int) -> bool:
    """判定 now 是否落在静默时段(分钟数口径,含起点不含终点)。
    起>止视为跨零点(深夜段);起==止视为空时段(永不静默)。"""
    t = now.hour * 60 + now.minute
    if q_start < q_end:
        return q_start <= t < q_end
    if q_start > q_end:
        return t >= q_start or t < q_end
    return False


def check_gates(now: datetime, params: dict, *, today_count: int, last_sent_ts: float | None,
                last_user_ts: float | None = None,
                roll: float | None = None) -> tuple[bool, str]:
    """门控判定(纯函数,便于单测)。依次:静默时段→每日上限→最小间隔→空闲阈值→概率。
    参数:
      today_count: 当日已主动发送条数;last_sent_ts: 上次主动发送 unix 秒(None=从未发过)
      last_user_ts: 对方最近一条消息 unix 秒;None=无记录(视为足够空闲,跳过该门)
      roll: 本次 tick 掷出的随机数 [0,1);None=跳过概率门(供调用方两段式判定,延迟取随机数)
    返回 (是否放行, 说明)。params 各键的含义与默认值见 plugin.yaml config_schema。
    参数类型脏(面板 JSON 混入非数值)时按防扰民原则 fail-closed 不放行、不抛异常。"""
    try:
        quiet = parse_quiet_hours(str(params.get("quiet_hours", "23:30-08:00")))
        if quiet is None:
            return False, "quiet_hours 配置非法(防扰民,本轮不发送)"
        if in_quiet_hours(now, *quiet):
            return False, "静默时段"
        daily_max = int(params.get("daily_max", 3))
        if daily_max <= 0 or today_count >= daily_max:
            return False, "已达每日上限"
        min_gap = float(params.get("min_gap_minutes", 120)) * 60
        if last_sent_ts is not None and now.timestamp() - float(last_sent_ts) < min_gap:
            return False, "距上次发送间隔不足"
        idle = float(params.get("idle_minutes", 90)) * 60
        if last_user_ts is not None and now.timestamp() - float(last_user_ts) < idle:
            return False, "对方刚聊过(空闲阈值未到)"
        if roll is not None and not (roll < float(params.get("prob", 0.05))):
            return False, "概率未命中"
    except (TypeError, ValueError):
        return False, "参数非法(防扰民,本轮不发送)"
    return True, "放行"


def _as_bool(val) -> bool:
    """布尔参数归一:bool 原样;其余按字符串口径("1"/"true"/"yes"/"on" 为真)。
    防面板 JSON 脏类型(如字符串 "false" 被 bool() 误判 True)意外开启语音。"""
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def is_farewell(text: str) -> bool:
    """对方末条消息是否为道别/就寝语(晚安感知门控用,纯函数便于单测)。
    命中任一道别词即 True——方向保守:误判只会少发不会多发(防扰民同向)。"""
    text = (text or "").strip()
    return any(w in text for w in _FAREWELL_WORDS)


def _sanitize_opener(text: str) -> str:
    """清洗模型产出:去首尾空白与成对包裹引号;空或超长(>_MAX_OPENER_LEN)返回 ""。
    不做风格改写——风格已由 OUTPUT_CONTRACT 约束(禁括号动作/句号结尾等),交由模型自律。"""
    text = (text or "").strip()
    if len(text) >= 2 and text[0] in _WRAP_QUOTES and text[-1] == _WRAP_QUOTES[text[0]]:
        text = text[1:-1].strip()
    if not text or len(text) > _MAX_OPENER_LEN:
        return ""
    return text


async def generate_opener(redis, oid: str, provider_name: str = "local") -> str:
    """生成本轮主动开场白(复用主链路口径;provider 不可用/产出为空返回 "" 由调用方跳过)。
    prompt 组装对齐 pipeline:render_system_prompt(末尾自带一次 OUTPUT_CONTRACT)
    → 追加 mood hint(仿 stage_mood_inject)→ 末尾再拼 OUTPUT_CONTRACT 压轴
    (仿 stage_build_messages 的 B-2 契约置末,压制 mood/记忆的语气诱导)。"""
    pid = await get_object_persona_id(redis, oid)
    card = await get_persona(redis, pid)
    if card is None:
        card = await get_default_persona(redis)   # 未绑定/人设缺失兜底(主链路同款)
    system_prompt = render_system_prompt(card, card.dynamic_state if card else None)
    state = await inject_hint(redis, oid)         # {mood,hint,label,kaomoji};无档位时 hint=""
    if state["hint"]:
        system_prompt += state["hint"]
    system_prompt += OUTPUT_CONTRACT              # 契约压轴(B-2 口径)
    history = await chat_store.get_history(redis, oid, max_messages=CONTEXT_MESSAGES)
    # 注入当前时辰(time_aware 同款纯函数),否则模型对"当前时段"只能瞎猜
    now = _now()
    time_hint = f"{season_label(now.month)}季·{time_of_day(now.hour)} {now.strftime('%H:%M')}"
    instruction = (
        f"[主动搭话] 现在是{time_hint},不是对话进行中,是你主动先给对方发一条消息开个话头。\n"
        "结合你的心情、当前时段和最近聊过的话题,写一句自然的开场消息。\n"
        "要求:20 到 60 个字;只输出这一句话本身;可以找话题或关心对方,但不要连环提问;"
        "严禁编造没发生过的约定或回忆——「说好的」「你答应过」这类说法,除非它真实出现在上面的对话里;"
        "不调用任何工具;绝不能出现「我作为AI」「作为助手」这类说法。"
    )
    messages = [Message(role="system", content=system_prompt)]
    messages.extend(history)                       # 最近对话(时间正序,旧→新)
    messages.append(Message(role="user", content=instruction))
    provider = resolve_provider("chat", override=provider_name)
    if provider is None:
        logger.warning("proactive_reply provider 不可用 name=%s,跳过本轮生成", provider_name)
        return ""
    resp = await provider.chat(messages)           # 一次性调用(local 路径已剥 <think> 段)
    text = _sanitize_opener(resp.text if resp else "")
    if not text:
        logger.info("proactive_reply 开场白生成为空/超长,丢弃 oid=%s", oid)
    return text


class ProactiveReplyPlugin(Plugin):
    """主动搭话:五重门控 + 本地模型开场白 + takeover 下发(全程软失败)"""

    async def on_tick(self, ctx):
        try:
            await self._maybe_proactive(ctx.object_id)
        except Exception:
            logger.exception("proactive_reply 处理异常 oid=%s(软失败,忽略本轮)", ctx.object_id)
        return HookResult.CONTINUE

    async def _maybe_proactive(self, oid: str) -> None:
        redis = self.pctx.redis
        params = await self.get_params(oid)
        now = _now()
        # 系统级静默优先于一切门控:AI 静默模式开/手动静默窗内绝不主动搭话
        # (与主回复链路 ws_client 同款检查;"AI 全闭嘴"是总开关,插件不得绕过)
        if await takeover_store.is_enabled(redis, oid) or await takeover_store.is_silenced(redis, oid):
            logger.debug("proactive_reply 静默模式/静默窗中,跳过 oid=%s", oid)
            return
        # 廉价门先行(静默/上限/间隔):只读 2 个状态键,不扫聊天历史
        count_key = _COUNT_KEY.format(oid=oid, day=now.strftime("%Y%m%d"))
        last_key = _LAST_KEY.format(oid=oid)
        today_count = int(await redis.get(count_key) or 0)
        last_sent_raw = await redis.get(last_key)
        last_sent_ts = float(last_sent_raw) if last_sent_raw else None
        ok, reason = check_gates(now, params, today_count=today_count, last_sent_ts=last_sent_ts)
        if not ok:
            logger.debug("proactive_reply 未命中 oid=%s 原因=%s", oid, reason)
            return
        # 昂贵检查置后:扫最近消息取对方最后发言(空闲门 + 晚安感知)+ 概率掷点
        last_user = await self._last_user_msg(redis, oid)
        last_user_ts = (int(last_user.get("ts", 0) or 0) / 1000.0) if last_user else None
        # 晚安感知门控(2026-10-27 加):对方末条是道别/就寝语 → 静默直到其再开口。
        # 判定只看"最后一条用户消息":道别后又发言则自然解除(末条不再是道别语)
        if _as_bool(params.get("farewell_aware", True)) and last_user is not None \
                and is_farewell(str(last_user.get("content", "") or "")):
            logger.debug("proactive_reply 对方已道别(晚安/睡了),静默至其再开口 oid=%s", oid)
            return
        ok, reason = check_gates(now, params, today_count=today_count, last_sent_ts=last_sent_ts,
                                 last_user_ts=last_user_ts, roll=random.random())
        if not ok:
            logger.debug("proactive_reply 未命中 oid=%s 原因=%s", oid, reason)
            return
        content = await generate_opener(redis, oid, str(params.get("llm_provider", "local")))
        if not content:
            return                                  # generate_opener 内已记日志
        use_tts = _as_bool(params.get("use_tts", False))
        try:
            result = await send_proactive(redis, oid, content, use_tts=use_tts)
            delivered, mode = result.get("delivered"), result.get("mode")
        except Exception:
            # 下发异常软失败不外抛,但状态照记(宁可少发不重发:
            # 落库后异常的路径消息已进历史,不记账会无界重试且 daily_max 失效)
            logger.exception("proactive_reply 下发异常 oid=%s(软失败,仍记状态防重试)", oid)
            delivered, mode = False, ""
        # 记状态(delivered=False 也计入:消息已落历史,重试同条易刷屏)
        await redis.set(last_key, int(now.timestamp()), ex=_LAST_TTL)
        count = await redis.incr(count_key)
        if count == 1:
            await redis.expire(count_key, _COUNT_TTL)
        logger.info("proactive_reply 已主动发送 oid=%s delivered=%s mode=%s 当日第%d条",
                    oid, delivered, mode, count)

    async def _last_user_msg(self, redis, oid: str) -> dict | None:
        """对方(用户)最近一条消息(含 ts 毫秒/content);无任何用户消息返回 None(视为足够空闲)。
        取最近少量消息倒序找 sender=user(list_messages 跨 block 按 ts 正序返回取尾);
        返回整条而非只返回时间戳,供空闲门(转秒)与晚安感知门(看 content)共用一次扫描。"""
        msgs = await chat_store.list_messages(redis, oid, limit=20)
        for m in reversed(msgs):
            if m.get("sender") == "user":
                return m
        return None
