"""
评分系统服务
每条 AI 回复自动 LLM 评分(对照人设打 0-100 基础分)+ 心情补偿(compute_mood_bias)+
score 四元组写入(chat_store.set_score)+ 正/负样本归类(驱动 reverse_infer 反推)+
手动改分 + 人设健康度统计。

评分流程(docs/01 §4 / docs/02 §5.1 / docs/03 §5):
  score_base  ← LLM 对照人设给回复打 0-100(人设契合度,与心情无关)
  mood_at_score ← 评分时刻读 mychat:mood:{oid} 当前 mood 值
  mood_bias  ← mood.service.compute_mood_bias(mood, kinds) = 档位.score_bias + uniform(-noise,noise)
  score      ← clamp(round(score_base + mood_bias), 0, 100)  ← 驱动正/负样本归类与反推
  归类       ← score>=positive_threshold→positive / <negative_threshold→negative / 其余 neutral

Redis 键:
  mychat:score:pos:{oid}   List  高分正样本(驱动反推示范,JSON: mid/text/score/ts,最近 N 条)
  mychat:score:neg:{oid}   List  低分负样本(驱动反推应避免,JSON 同上)

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 新建 score service:LLM 评分(score_reply/_llm_score/_parse_score)+ classify 阈值归类
     + 样本收集(_collect_sample/list_samples)+ manual_set_score(手动改分重算)+
     get_score + persona_health(近 N 条均分/正负计数)

2026-06-30
变更说明:
  1. M7 新增 record_negative_sample(公开写 neg 队列,供 rest_chat 软删联动扩充反推负样本)

2026-08-18
变更说明:
  1. manual_set_score 加 corrected 参数(管理员纠正回复:写消息字段 + 正样本 source=correction
     进反推队列,原 content 不动) + 样本同步(改分后按新 score 清旧重收,手动打分同样驱动反推);
     get_score 返回 corrected

2026-09-07
变更说明:
  1. score_reply 加 force_positive 参数(手动回复评分,NapCat message_sent 链路):LLM 四元组
     照算(展示/健康度),样本恒正 source='manual' score=100(管理员亲手回复=黄金标准,同 correction
     待遇,不参与 classify);LLM 评分失败(返 None)时正样本仍单独收集(黄金标准不依赖 LLM 可用性)
"""
import json
import logging
import time

from redis.asyncio import Redis

from llm.base import Message
from llm.resolver import resolve_provider, resolve_provider_name
from persona.renderer import render_system_prompt
from core.config import settings

logger = logging.getLogger(__name__)

# 正/负样本采集键(List,LPUSH 新样本在前,LTRIM 裁剪保留最近 N 条)
_K_POS = "mychat:score:pos:{oid}"
_K_NEG = "mychat:score:neg:{oid}"

# 纯媒体占位文本(2026-09-07 审查修复):手动回复为占位时(管理员发了语音/图片等)不作
# 黄金正样本收进反推队列——"[语音]"这类文本对提炼人设风格毫无价值,反而污染权威样本池
_PLACEHOLDER_TEXTS = {"[语音]", "[图片]", "[表情]", "[转发]", "[文件]", "[视频]", "[非文本消息]"}


def _now_ms() -> int:
    """当前毫秒时间戳"""
    return int(time.time() * 1000)


def classify(score: int) -> str:
    """按阈值把最终分 score 归类(docs/01 §4 / docs/02 §5.1):
    positive(score>=positive_threshold)/ negative(score<negative_threshold)/ neutral"""
    if score >= settings.score_positive_threshold:
        return "positive"
    if score < settings.score_negative_threshold:
        return "negative"
    return "neutral"


# ================ LLM 评分(对照人设打基础分)================

async def _llm_score(reply_text: str, persona_card, provider_name: str, model: str):
    """调 LLM 对照人设给回复打基础分 score_base(0-100,人设契合度,与心情无关)。
    返回 (score_base, reason);无可用 provider 或调用失败返回 None。"""
    provider = resolve_provider("score", provider_name)
    if provider is None:
        logger.info("评分跳过:provider 未配置 key(name=%s)", resolve_provider_name("score", provider_name))
        return None
    # 人设摘要作评审基准(renderer 输出 system_prompt 形态,含性格/画像/说话风格/示例对话)
    persona_brief = render_system_prompt(persona_card, None) if persona_card is not None else ""
    prompt = (
        "你是人设契合度评审。请严格对照下方【角色人设】,评估这条【角色回复】在"
        "语气、性格、说话风格、人设一致性上的契合度,打 0-100 的基础分(越高越符合人设,与心情无关),"
        "并给出简短理由(一句话,指出契合或偏离之处)。\n"
        "严格只输出一个 JSON 对象:{\"score\": <0-100 整数>, \"reason\": <一句话理由>}。\n\n"
        f"【角色人设】\n{persona_brief or '(未提供人设,按通用友善助手标准评)'}\n\n"
        f"【角色回复(待评)】\n{reply_text}\n"
    )
    try:
        resp = await provider.chat([Message(role="user", content=prompt)],
                                   model=model or settings.score_model or "")
        return _parse_score(resp.text)
    except Exception as e:
        logger.warning("评分 LLM 调用失败: %s", e)
        return None


def _parse_score(text: str):
    """从 LLM 输出解析 {score, reason}。容错:扫描首个 score 可解析为整数的 JSON 对象
    (含 score 但值非数的对象跳过继续找,保留原语义)。解析逻辑收口于 llm.json_extract。"""
    from llm.json_extract import extract_json_object

    def _valid_score(d):
        if "score" not in d:
            return False
        try:
            int(round(float(d["score"])))
            return True
        except (TypeError, ValueError):
            return False

    obj = extract_json_object(text, predicate=_valid_score)
    if obj is None:
        return None
    sc = max(0, min(100, int(round(float(obj["score"])))))
    return sc, str(obj.get("reason", ""))


# ================ 自动评分主入口(pipeline 调)================

async def score_reply(redis: Redis, object_id: str, reply_text: str,
                      persona_card, mid: str, *,
                      mood_value: float | None = None,
                      provider_name: str = "", model: str = "",
                      force_positive: bool = False) -> dict | None:
    """对一条 ai 回复自动评分:LLM 打 score_base → 心情补偿 mood_bias → 写 score 四元组 → 样本归类。
    返回四元组 dict(含 score_base/mood_at_score/mood_bias/score/score_reason);
    评分失败(无 provider/LLM 异常/解析失败)返回 None,调用方应容错跳过。
    force_positive(2026-09-07,手动回复专用):样本不按 classify 归类,恒为正样本
    source='manual' score=100(管理员亲手回复=黄金标准,同 correction 待遇);LLM 四元组照算
    (仅展示/健康度用);LLM 评分失败(返 None)时正样本仍单独收集(黄金标准不依赖 LLM 可用性)。"""
    from mood import service as mood_service
    from storage import chat_store

    result = await _llm_score(reply_text, persona_card, provider_name, model)
    if result is not None:
        score_base, reason = result
        # 评分时刻 mood(mood_bias 补偿依据;优先用调用方传入的 ctx.mood_value,避免重复读)
        mood = mood_value if mood_value is not None else await mood_service.get_mood(redis, object_id)
        mood_bias = await mood_service.bias_for(redis, mood)   # list_kinds+compute_mood_bias 收口(架构 #5)
        # 写 score 四元组(chat_store.set_score 算 score=clamp(base+bias))
        quad = await chat_store.set_score(redis, mid,
                                          score_base=score_base, mood_value=mood, mood_bias=mood_bias)
        # 额外存 score_reason 到消息 Hash(面板展示用,非四元组字段)
        if reason:
            await redis.hset(f"mychat:msg:{mid}", "score_reason", reason)
        quad["score_reason"] = reason
        if force_positive:
            if (reply_text or "").strip() not in _PLACEHOLDER_TEXTS:
                await _collect_sample(redis, object_id, "positive", mid, reply_text, 100, source="manual")
        else:
            # 正/负样本归类收集(驱动 reverse_infer;neutral 不收集)
            kind = classify(quad["score"])
            if kind in ("positive", "negative"):
                await _collect_sample(redis, object_id, kind, mid, reply_text, quad["score"])
        return quad
    # LLM 评分失败:force_positive 仍收正样本(手动回复是既成事实的黄金样本,不依赖 LLM;
    # 占位文本除外——[语音]/[图片]对反推无价值)
    if force_positive and (reply_text or "").strip() not in _PLACEHOLDER_TEXTS:
        await _collect_sample(redis, object_id, "positive", mid, reply_text, 100, source="manual")
    return None


async def _collect_sample(redis: Redis, object_id: str, kind: str,
                          mid: str, text: str, score: int,
                          source: str = "dialog") -> None:
    """把评分样本收集到 pos/neg List(供 reverse_infer),LPUSH+LTRIM 保留最近 N 条。
    source(2026-07-07):样本来源标记 dialog(真实对话)/roleplay(训练剧本),写入 payload,
    供 reverse_infer 按 source 区分对待(真实对话权威,剧本参考)——修 score 队列
    roleplay/live 共池无 source 区分的已存在污染。"""
    key = (_K_POS if kind == "positive" else _K_NEG).format(oid=object_id)
    payload = json.dumps({"mid": mid, "text": text, "score": score,
                          "ts": _now_ms(), "source": source}, ensure_ascii=False)
    pipe = redis.pipeline()
    pipe.lpush(key, payload)                                   # 新样本在前
    pipe.ltrim(key, 0, settings.score_sample_keep - 1)         # 裁剪保留最近 N 条
    await pipe.execute()


# ================ 手动改分 / 取分(Web 面板 M7 调,M3 先建接口)================

async def manual_set_score(redis: Redis, mid: str, score_base: int,
                           score_note: str | None = None,
                           corrected: str | None = None,
                           corrected_score: int | None = None) -> dict | None:
    """手动改分:覆盖 score_base;mood_bias 保留原值(原为空则按原 mood_at_score 重算);
    重算 score=clamp(base+mood_bias)。score_note(2026-07-07):评分批注,说明为什么这个分。
    corrected(2026-08-18):管理员纠正回复——更符合人设的理想回复,原消息 content 保留不动
    (QQ 已发出的无法撤回重发,纠正只用于学习)。非空时写消息 corrected 字段 + 作为正样本
    (source=correction,反推最高权威)进 pos 队列;空串=清除纠正;None=未提供(不动该字段)。
    corrected_score(2026-08-18 #2):纠正回复的分数(纠正版"有多理想",仅记录/展示,
    恒为正样本不参与 classify);None=默认 100,沿用消息已存值。
    样本同步(2026-08-18):改分后按新 score 重新归类样本(先 remove_sample_by_mid 清旧再按
    新分收集)——修"手动打负分不进 neg 队列/手动改分后反推仍读旧分样本"的缺口。
    返回新四元组;消息不存在返回 None。设计:手动改分尊重评分时刻的历史心情,只改基础分。"""
    from storage import chat_store
    from mood import service as mood_service

    msg = await chat_store.get_message(redis, mid)
    if not msg:
        return None
    score_base = max(0, min(100, int(round(score_base))))
    # 原 mood_bias(空串表未评分过)
    raw_bias = msg.get("mood_bias", "")
    has_bias = raw_bias not in ("", None)
    try:
        mood_bias = float(raw_bias) if has_bias else 0.0
    except (TypeError, ValueError):
        mood_bias, has_bias = 0.0, False
    # 原 mood_at_score(重算 mood_bias 与回填四元组用)
    try:
        mood_value = float(msg.get("mood_at_score", "") or 0.5) or 0.5
    except (TypeError, ValueError):
        mood_value = 0.5
    oid = msg.get("object_id", "")
    if not has_bias:
        # 原未自动评分过:用原 mood_at_score 重算一次 mood_bias(保留心情影响语义)
        if oid:
            mood_bias = await mood_service.bias_for(redis, mood_value)   # 收口(架构 #5)
    quad = await chat_store.set_score(redis, mid,
                                      score_base=score_base, mood_value=mood_value, mood_bias=mood_bias,
                                      score_note=score_note)
    await redis.hset(f"mychat:msg:{mid}", "score_manual", "1")   # 标记手动覆盖(面板区分)
    quad["score_manual"] = "1"
    # —— 样本同步:按新 score 重新归类(手动打分同样驱动反推;清旧防残留)——
    orig_text = msg.get("content", "")
    # 有效纠正文本:显式传入优先;未传(None)沿用消息已存纠正(重收后须重建 correction 样本,
    # 否则 remove_sample_by_mid 会把同 mid 的纠正样本一并清掉而无人补回)
    eff_corrected = ((corrected or "").strip() if corrected is not None
                     else (msg.get("corrected", "") or "").strip())
    # 有效纠正分数:显式传入优先;未传(None)沿用消息已存值;再兜底 100
    if corrected_score is not None:
        eff_score = max(0, min(100, int(round(corrected_score))))
    else:
        try:
            eff_score = int(float(msg.get("corrected_score", "") or 100))
        except (TypeError, ValueError):
            eff_score = 100
    if oid:
        await remove_sample_by_mid(redis, oid, mid)
        kind = classify(quad["score"])
        if kind in ("positive", "negative") and orig_text:
            await _collect_sample(redis, oid, kind, mid, orig_text, quad["score"], source="dialog")
    # —— 纠正回复:写消息字段 + 正样本进反推(管理员改写=黄金标准)——
    if corrected is not None:
        c = (corrected or "").strip()
        await redis.hset(f"mychat:msg:{mid}", "corrected", c)
        quad["corrected"] = c
    if corrected_score is not None:   # 只调纠正分数(不重填文本)也落库
        await redis.hset(f"mychat:msg:{mid}", "corrected_score", str(eff_score))
    if eff_corrected:                 # 有纠正即回显有效纠正分数(面板免二次查询)
        quad["corrected_score"] = eff_score
    if eff_corrected and oid:
        await _collect_sample(redis, oid, "positive", mid, eff_corrected, eff_score, source="correction")
    return quad


async def get_score(redis: Redis, mid: str) -> dict | None:
    """取 score 四元组(+ score_reason/score_manual 标记)。消息不存在返回 None。
    数值字段从 Redis Hash 的 str 转回 int/float(未评分时为 None),便于面板/反推直接使用。"""
    from storage import chat_store
    msg = await chat_store.get_message(redis, mid)
    if not msg:
        return None

    def _num(cast, v):
        """Redis Hash str → 数值;空串/非法返 None"""
        if v in ("", None):
            return None
        try:
            return cast(v)
        except (TypeError, ValueError):
            return None

    return {
        "mid": mid,
        "score_base": _num(int, msg.get("score_base", "")),
        "mood_at_score": _num(float, msg.get("mood_at_score", "")),
        "mood_bias": _num(float, msg.get("mood_bias", "")),
        "score": _num(int, msg.get("score", "")),
        "score_reason": msg.get("score_reason", ""),
        "score_manual": msg.get("score_manual", ""),
        "score_note": msg.get("score_note", ""),   # 评分批注(2026-07-07)
        "corrected": msg.get("corrected", ""),     # 管理员纠正回复(2026-08-18,原内容保留)
        "corrected_score": _num(int, msg.get("corrected_score", "")),   # 纠正回复分数(默认 100)
    }


# ================ 人设健康度(docs/01 §4)================

async def persona_health(redis: Redis, object_id: str, *, window: int | None = None) -> dict:
    """人设健康度:近 window 条 ai/proxy 消息的 score 均分 + 正/负/中样本计数。
    低均分预警"人设跑偏"。window 默认 score_health_window。"""
    from storage import chat_store
    window = settings.score_health_window if window is None else window
    # 多取些再筛 ai/proxy(scored 取最近 window 条有分的)
    msgs = await chat_store.list_messages(redis, object_id, limit=max(window * 3, 60))
    scored: list[int] = []
    for m in reversed(msgs):   # 最近在前
        if m.get("sender", "") not in ("ai", "proxy"):
            continue
        raw = m.get("score", "")
        if raw in ("", None):
            continue
        try:
            scored.append(int(float(raw)))
        except (TypeError, ValueError):
            continue
        if len(scored) >= window:
            break
    if not scored:
        return {"object_id": object_id, "avg_score": None, "count": 0,
                "positive": 0, "negative": 0, "neutral": 0}
    avg = round(sum(scored) / len(scored), 1)
    pos = sum(1 for s in scored if s >= settings.score_positive_threshold)
    neg = sum(1 for s in scored if s < settings.score_negative_threshold)
    return {"object_id": object_id, "avg_score": avg, "count": len(scored),
            "positive": pos, "negative": neg, "neutral": len(scored) - pos - neg}


# ================ 样本读取(反推 / 面板用)================

async def list_samples(redis: Redis, object_id: str, kind: str) -> list[dict]:
    """列正/负样本(供 reverse_infer / Web 面板)。kind='positive'/'negative'。"""
    key = (_K_POS if kind == "positive" else _K_NEG).format(oid=object_id)
    raw = await redis.lrange(key, 0, -1)
    out = []
    for x in raw:
        try:
            d = json.loads(x)
            if isinstance(d, dict):
                out.append(d)
        except (json.JSONDecodeError, TypeError):
            pass
    return out


async def record_negative_sample(redis: Redis, object_id: str,
                                 mid: str, text: str, score: int) -> None:
    """公开入口:把一条负样本写入 neg 队列(供 reverse_infer 反推)。
    供软删联动调用(rest_chat DELETE ai/proxy 消息时,扩充反推负样本数据源)。
    内部复用 _collect_sample(kind="negative"),保证数据结构与评分自动归类一致({mid,text,score,ts})。"""
    await _collect_sample(redis, object_id, "negative", mid, text, score)


async def record_score_sample(redis: Redis, object_id: str,
                              mid: str, text: str, score: int,
                              source: str = "roleplay") -> None:
    """按 score 阈值归类记录到 pos/neg 样本队列(2026-07-05 roleplay 评分联动反推用)。
    neutral 不记。复用 _collect_sample。改分/删前应先 remove_sample_by_mid 清旧,避免脏数据。
    source(2026-07-07,默认 roleplay):本函数供 roleplay 评分联动(chat_store.append_roleplay_message
    /set_roleplay_score),故默认打 source='roleplay';reverse_infer 据此区分真实对话/训练剧本样本
    (真实权威,剧本参考),修 score 队列 roleplay/live 共池无区分的已存在污染。"""
    kind = classify(score)
    if kind in ("positive", "negative"):
        await _collect_sample(redis, object_id, kind, mid, text, score, source=source)


async def remove_sample_by_mid(redis: Redis, object_id: str, mid: str) -> None:
    """从 pos/neg 样本队列移除指定 mid 的样本(2026-07-05 改分/删除前清旧)。
    队列短(≤score_sample_keep)遍历 + lrem 精确删 payload。无该 mid 无副作用。"""
    for key in (_K_POS.format(oid=object_id), _K_NEG.format(oid=object_id)):
        for it in await redis.lrange(key, 0, -1):
            try:
                if json.loads(it).get("mid") == mid:
                    await redis.lrem(key, 1, it)
            except (json.JSONDecodeError, TypeError):
                pass
