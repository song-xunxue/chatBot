"""
反推人设·评分驱动直接合并(M3)
数据源:评分正样本(高分 ai 回复,作人设示范)+ 评分负样本(低分 ai 回复,应避免风格)。
调 LLM 提炼人设字段 → 字段白名单过滤 + drift 幅度校验 + 两步契约
(dry_run 返回 diff+confirm_token,apply 凭 token 落库),合并前快照入
PersonaCard.history 支持回滚。

改造自 V1.0 persona/reverse_infer.py(数据源 roleplay→评分样本),对应
docs/01 §4(评分驱动反推)/ docs/02 §5.1(score<60 负样本 / score>85 正样本)。

两步契约:预览不可绕过——apply 必须携带 dry_run 返回的 confirm_token(绑定 diff 内容),
防止人设被误改/绕过评审直接落库。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 新建 reverse_infer:从 V1.0 移植 infer_and_merge 两步契约骨架(白名单/drift/snapshot/
     字段读写),数据源改为 score 正/负样本(score.service.list_samples),prompt 适配单条回复文本
"""
import difflib
import json
import logging
import secrets

from llm.base import Message
from llm.resolver import resolve_provider
from persona import store as persona_store
from score import service as score_service
from core.config import settings

logger = logging.getLogger(__name__)

# 反推可改写字段白名单(核心身份字段 name/id/avatar/model/plugins 等永不被改)
FIELD_WHITELIST = {
    "personality", "speech_style", "catchphrase", "age", "gender",
    "occupation", "appearance", "race", "likes", "dislikes",
    "relationship", "greeting", "scenario", "description",
}
# 顶层字段(直接挂在 PersonaCard)
_TOP = {"personality", "scenario", "description"}
# 嵌套字段 → 所属子结构
_NESTED = {
    "age": "profile", "gender": "profile", "occupation": "profile", "appearance": "profile",
    "race": "profile", "speech_style": "profile", "catchphrase": "profile",
    "likes": "preferences", "dislikes": "preferences",
    "relationship": "relationship", "greeting": "relationship",
}
# 单字段字符上限(防 LLM 输出过长)
MAX_FIELD_CHARS = {
    "catchphrase": 30, "age": 8, "gender": 6, "speech_style": 120, "occupation": 30,
    "race": 20, "appearance": 200, "relationship": 30, "greeting": 100,
    "personality": 300, "description": 400, "scenario": 400,
}

# 两步契约暂存键(diff + pid,EXPIRE 600s)
_K_PENDING = "mychat:reverse_infer:pending:{token}"


# —— 字段读写(处理 PersonaCard 嵌套结构)——

def _get_card_value(card, field: str):
    """按白名单字段名读 PersonaCard 对应值(顶层/嵌套 profile/preferences/relationship)"""
    if field in _TOP:
        return getattr(card, field, "")
    if field == "relationship":
        return getattr(card.relationship, "relation", "")
    parent = _NESTED.get(field)
    if parent == "profile":
        return getattr(card.profile, field, "")
    if parent == "preferences":
        return getattr(card.preferences, field, [])
    if parent == "relationship":
        return getattr(card.relationship, field, "")
    return ""


def _set_card_value(card, field: str, value) -> None:
    """按白名单字段名写 PersonaCard 对应值(顶层/嵌套)"""
    if field in _TOP:
        setattr(card, field, value)
        return
    if field == "relationship":
        setattr(card.relationship, "relation", value)
        return
    parent = _NESTED.get(field)
    if parent == "profile":
        setattr(card.profile, field, value)
    elif parent == "preferences":
        # likes/dislikes:LLM 可能输出逗号字符串或数组,统一为数组
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        setattr(card.preferences, field, value)
    elif parent == "relationship":
        setattr(card.relationship, field, value)


# —— JSON 解析(容忍 LLM 输出前后多余文本)——

def _parse_json_object(text: str) -> dict:
    """从 LLM 输出解析首个 JSON 对象(raw_decode 容忍前后多余文本)"""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text or ""):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


# —— diff 构建(白名单 + 幅度 + 截断)——

def _drift_too_large(old: str, new: str) -> bool:
    """drift 度量:字符级差异比例 > 60% 视为漂移过大(仅 overwrite 模式用)"""
    if not old:
        return False
    ratio = difflib.SequenceMatcher(None, str(old), str(new)).ratio()
    return (1 - ratio) > 0.6


def _build_diff(card, extracted: dict, mode: str = "fill_empty") -> dict:
    """构建字段 diff。mode=fill_empty(只填空)/ overwrite(覆盖但查漂移)。
    返回 {field: {old, new, action}},最多 reverse_infer_max_fields 个。"""
    diff = {}
    for field, new_val in extracted.items():
        if field not in FIELD_WHITELIST:
            continue   # 越权字段丢弃
        old = _get_card_value(card, field)
        if mode == "fill_empty" and old:
            continue   # fill_empty:已有值不覆盖
        # 归一化新值(list 保留,字符串截断到字段上限)
        if isinstance(new_val, list):
            new_norm = [str(v).strip() for v in new_val if str(v).strip()]
        else:
            new_norm = str(new_val).strip()
            limit = MAX_FIELD_CHARS.get(field, 200)
            if len(new_norm) > limit:
                new_norm = new_norm[:limit]
        if new_norm in ("", []):
            continue
        if mode != "fill_empty" and _drift_too_large(str(old), str(new_norm)):
            continue   # overwrite 模式漂移过大跳过
        if old == new_norm:
            continue
        diff[field] = {"old": old, "new": new_norm, "action": "update"}
        if len(diff) >= settings.reverse_infer_max_fields:
            break
    return diff


def _make_token() -> str:
    """生成两步契约确认 token"""
    return secrets.token_hex(8)


# —— LLM 提炼(评分样本 → 人设字段 JSON)——

async def _llm_extract(positives: list[str], negatives: list[str], llm) -> dict:
    """调 LLM 从评分样本提炼人设字段 JSON。positives/negatives 为回复文本列表。失败返回 {}。"""
    pos_txt = "\n".join(f"- {p}" for p in positives[:20]) if positives else "(无)"
    neg_txt = "\n".join(f"- {n}" for n in negatives[:10]) if negatives else "(无)"
    prompt = (
        "你是人设分析师。以下是某角色在与用户对话中获得高分的优秀回复(正样本,契合人设应保持的风格),"
        "以及获得低分的偏离回复(负样本,应避免的风格)。请据此提炼该角色的人设字段。\n"
        "只输出一个 JSON 对象,键为人设字段名,值为提炼结果。\n"
        "可选字段:personality, speech_style, catchphrase, age, gender, occupation, appearance, race, "
        "likes(字符串数组), dislikes(字符串数组), relationship, greeting, scenario, description。\n"
        "只输出有把握的字段,没有依据就不要输出该字段。严格只输出 JSON,不要解释。\n\n"
        f"【高分优秀回复(正样本,应贴合的风格)】\n{pos_txt}\n\n"
        f"【低分偏离回复(负样本,应避免的风格)】\n{neg_txt}\n"
    )
    try:
        resp = await llm.chat([Message(role="user", content=prompt)])
        return _parse_json_object(resp.text)
    except Exception as e:
        logger.warning("reverse_infer LLM 调用失败: %s", e)
        return {}


# —— 主入口(两步契约)——

async def infer_and_merge(redis, object_id: str, *,
                          mode: str | None = None, dry_run: bool = True,
                          confirm_token: str = "", provider_name: str = "") -> dict:
    """反推合并主入口(评分样本驱动)。
    dry_run=True:取评分正/负样本→LLM 提炼→构建 diff→暂存(token)→返回 {diff, confirm_token, ...}
    dry_run=False:凭 confirm_token 取暂存 diff→snapshot→合并→set→返回 {merged, pid, diff, card}。
    预览不可绕过:apply 必须携带 dry_run 返回的 token(绑定 diff 内容)。"""
    mode = mode or settings.reverse_infer_mode
    pid = await persona_store.get_object_persona_id(redis, object_id)

    if dry_run:
        card = await persona_store.get_persona(redis, pid)
        if not card:
            return {"aborted_reason": "persona_not_found"}
        positives = await score_service.list_samples(redis, object_id, "positive")
        negatives = await score_service.list_samples(redis, object_id, "negative")
        pos_texts = [s.get("text", "") for s in positives if s.get("text")]
        neg_texts = [s.get("text", "") for s in negatives if s.get("text")]
        if not pos_texts and not neg_texts:
            return {"aborted_reason": "no_samples", "diff": {}}
        llm = resolve_provider("reverse_infer", provider_name)
        if llm is None:
            return {"aborted_reason": "no_llm_provider", "diff": {}}
        extracted = await _llm_extract(pos_texts, neg_texts, llm)
        if not extracted:
            return {"aborted_reason": "llm_empty_or_failed", "diff": {}}
        diff = _build_diff(card, extracted, mode)
        token = _make_token()
        await redis.set(_K_PENDING.format(token=token),
                        json.dumps({"pid": pid, "object_id": object_id, "diff": diff},
                                   ensure_ascii=False), ex=600)
        return {"diff": diff, "confirm_token": token,
                "positive_count": len(pos_texts), "negative_count": len(neg_texts)}

    # apply:凭 token 落库
    if not confirm_token:
        return {"aborted_reason": "no_token"}
    raw = await redis.get(_K_PENDING.format(token=confirm_token))
    if not raw:
        return {"aborted_reason": "token_expired_or_invalid"}
    data = json.loads(raw)
    pid = data["pid"]
    diff = data["diff"]
    card = await persona_store.get_persona(redis, pid)
    if not card:
        return {"aborted_reason": "persona_not_found"}
    await persona_store.snapshot_persona(redis, pid)   # 合并前快照(写 history,支持回滚)
    card = await persona_store.get_persona(redis, pid)   # 重读含快照 history,避免 set 覆盖
    for field, change in diff.items():
        _set_card_value(card, field, change["new"])
    await persona_store.set_persona(redis, card)
    await redis.delete(_K_PENDING.format(token=confirm_token))
    return {"merged": True, "pid": pid, "diff": diff, "card": card.to_dict()}
