"""
反推人设·直接合并（V1.1 M12）
从 roleplay 正样本（代人代答对话）+ 删除负样本，调 LLM 提炼人设字段，
经字段白名单 + drift 幅度校验 + 两步契约（dry_run 返回 diff+confirm_token，
apply 凭 token 落库），合并前快照入 PersonaCard.history 支持回滚。
对应 docs/10 §7。决策3：直接合并 + 两步预览（预览不可绕过）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. V1.1 M12 创建 reverse_infer：infer_and_merge（dry_run/apply 两步）+ 白名单 + drift + 截断
"""
import difflib
import json
import logging
import secrets

from llm.base import Message
from llm.registry import get_provider, available_providers
from persona import store as persona_store
from storage import chat_store

logger = logging.getLogger(__name__)

# 反推可改写字段白名单（核心身份字段 name/id/avatar/model/plugins 等永不被改）
FIELD_WHITELIST = {
    "personality", "speech_style", "catchphrase", "age", "gender",
    "occupation", "appearance", "race", "likes", "dislikes",
    "relationship", "greeting", "scenario", "description",
}
# 顶层字段（直接挂在 PersonaCard）
_TOP = {"personality", "scenario", "description"}
# 嵌套字段 → 所属子结构
_NESTED = {
    "age": "profile", "gender": "profile", "occupation": "profile", "appearance": "profile",
    "race": "profile", "speech_style": "profile", "catchphrase": "profile",
    "likes": "preferences", "dislikes": "preferences",
    "relationship": "relationship", "greeting": "relationship",
}
# 单字段字符上限（防 LLM 输出过长）
MAX_FIELD_CHARS = {
    "catchphrase": 30, "age": 8, "gender": 6, "speech_style": 120, "occupation": 30,
    "race": 20, "appearance": 200, "relationship": 30, "greeting": 100,
    "personality": 300, "description": 400, "scenario": 400,
}
MAX_FIELDS_TOUCHED = 6          # 单次合并最多改 6 字段（整体接受，不按幅度截断拆散语义）
_REVERSE_INFER_PROVIDER = "glm"  # 反推专用 provider（与聊天解耦，无 key 降级空 diff）

# Redis 键
_K_PENDING = "mychat:reverse_infer:pending:{token}"        # 两步契约暂存（diff + pid，EXPIRE 600s）
_K_NEG = "mychat:roleplay:neg:{oid}"                        # roleplay 删除负样本（M11）
_K_EVOLVE_SAMPLES = "mychat:persona_evolve:samples:{oid}"   # 真实删除负样本（M4.4 persona_evolve）


# —— 字段读写（处理 PersonaCard 嵌套结构）——

def _get_card_value(card, field: str):
    if field in _TOP:
        return getattr(card, field, "")
    if field == "relationship":
        return getattr(card.relationship, "relation", "")   # V1.2 fix: 字段名 relation（非 relationship）
    parent = _NESTED.get(field)
    if parent == "profile":
        return getattr(card.profile, field, "")
    if parent == "preferences":
        return getattr(card.preferences, field, [])
    if parent == "relationship":
        return getattr(card.relationship, field, "")
    return ""


def _set_card_value(card, field: str, value) -> None:
    if field in _TOP:
        setattr(card, field, value)
        return
    if field == "relationship":
        setattr(card.relationship, "relation", value)   # V1.2 fix: 字段名 relation（非 relationship）
        return
    parent = _NESTED.get(field)
    if parent == "profile":
        setattr(card.profile, field, value)
    elif parent == "preferences":
        # likes/dislikes：LLM 可能输出逗号字符串或数组，统一为数组
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        setattr(card.preferences, field, value)
    elif parent == "relationship":
        setattr(card.relationship, field, value)


# —— 样本采集 ——

async def _collect_negatives(redis, oid: str) -> list[str]:
    """负样本：roleplay 删除（M11 neg 队列）+ 真实删除（persona_evolve samples）"""
    negs = []
    for x in await redis.lrange(_K_NEG.format(oid=oid), 0, -1):
        try:
            negs.append(json.loads(x).get("text", ""))
        except Exception:
            pass
    evolve_raw = await redis.get(_K_EVOLVE_SAMPLES.format(oid=oid))
    if evolve_raw:
        try:
            for s in json.loads(evolve_raw):
                if isinstance(s, dict):
                    negs.append(s.get("text", ""))
        except Exception:
            pass
    return [n for n in negs if n]


# —— LLM 提炼 ——

async def _llm_extract(positives: list[dict], negatives: list[str], llm) -> dict:
    """调 LLM 从样本提炼人设字段 JSON。失败返回 {}。"""
    dialog = "\n".join(f"{m['role']}: {m['content']}" for m in positives[-20:])
    neg_txt = "\n".join(f"- {n}" for n in negatives[:10]) if negatives else "（无）"
    prompt = (
        "你是人设分析师。根据以下角色与用户的示范对话（正样本）和不符合人格的回复（负样本，应避免），"
        "提炼这个角色的人设字段。只输出一个 JSON 对象，键为人设字段名，值为提炼结果。\n"
        "可选字段：personality, speech_style, catchphrase, age, gender, occupation, appearance, race, "
        "likes(字符串数组), dislikes(字符串数组), relationship, greeting, scenario, description。\n"
        "只输出有把握的字段，没有依据就不要输出该字段。严格只输出 JSON，不要解释。\n\n"
        f"【示范对话（正样本）】\n{dialog}\n\n"
        f"【不符合人格的回复（负样本，应避免的风格）】\n{neg_txt}\n"
    )
    try:
        resp = await llm.chat([Message(role="user", content=prompt)])
        return _parse_json_object(resp.text)
    except Exception as e:
        logger.warning("reverse_infer LLM 调用失败: %s", e)
        return {}


def _parse_json_object(text: str) -> dict:
    """从 LLM 输出解析首个 JSON 对象（raw_decode 容忍前后多余文本）"""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


# —— diff 构建（白名单 + 幅度 + 截断）——

def _drift_too_large(old: str, new: str) -> bool:
    """drift 度量：字符级差异比例 > 60% 视为漂移过大（仅 overwrite 模式用）"""
    if not old:
        return False
    ratio = difflib.SequenceMatcher(None, str(old), str(new)).ratio()
    return (1 - ratio) > 0.6


def _build_diff(card, extracted: dict, mode: str = "fill_empty") -> dict:
    """构建字段 diff。mode=fill_empty（只填空）/ overwrite（覆盖但查漂移）。
    返回 {field: {old, new, action}}，最多 MAX_FIELDS_TOUCHED 个。"""
    diff = {}
    for field, new_val in extracted.items():
        if field not in FIELD_WHITELIST:
            continue   # 越权字段丢弃
        old = _get_card_value(card, field)
        if mode == "fill_empty" and old:
            continue   # fill_empty：已有值不覆盖
        # 归一化新值
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
        if len(diff) >= MAX_FIELDS_TOUCHED:
            break
    return diff


def _make_token() -> str:
    return secrets.token_hex(8)


# —— 主入口（两步契约）——

async def infer_and_merge(redis, object_id: str, mode: str = "fill_empty",
                          dry_run: bool = True, confirm_token: str = "",
                          provider_name: str = "") -> dict:
    """反推合并主入口。
    dry_run=True：读样本→LLM 提炼→构建 diff→暂存(token)→返回 {diff, confirm_token, ...}
    dry_run=False：凭 confirm_token 取暂存 diff→snapshot→合并→set→返回 {merged, card, diff}。
    预览不可绕过：apply 必须携带 dry_run 返回的 token（绑定 diff 内容）。"""
    pid = await persona_store.get_object_persona_id(redis, object_id)

    if dry_run:
        card = await persona_store.get_persona(redis, pid)
        if not card:
            return {"aborted_reason": "persona_not_found"}
        positives = await chat_store.list_roleplay(redis, object_id)
        if not positives:
            return {"aborted_reason": "no_positive_samples", "diff": {}}
        negatives = await _collect_negatives(redis, object_id)
        pname = provider_name or _REVERSE_INFER_PROVIDER
        if pname not in available_providers():
            return {"aborted_reason": "no_llm_provider", "diff": {}}
        llm = get_provider(pname)
        extracted = await _llm_extract(positives, negatives, llm)
        if not extracted:
            return {"aborted_reason": "llm_empty_or_failed", "diff": {}}
        diff = _build_diff(card, extracted, mode)
        token = _make_token()
        await redis.set(_K_PENDING.format(token=token),
                        json.dumps({"pid": pid, "object_id": object_id, "diff": diff},
                                   ensure_ascii=False), ex=600)
        return {"diff": diff, "confirm_token": token,
                "positive_count": len(positives), "negative_count": len(negatives)}

    # apply：凭 token 落库
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
    await persona_store.snapshot_persona(redis, pid)   # 合并前快照（写 history，支持回滚）
    card = await persona_store.get_persona(redis, pid)   # 重新读含快照的 history，避免 set 覆盖
    for field, change in diff.items():
        _set_card_value(card, field, change["new"])
    await persona_store.set_persona(redis, card)
    await redis.delete(_K_PENDING.format(token=confirm_token))
    return {"merged": True, "pid": pid, "diff": diff, "card": card.to_dict()}
