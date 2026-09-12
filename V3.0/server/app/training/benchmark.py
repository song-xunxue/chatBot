"""
人设盲测基准(前置工作 A2,2026-09-12)
同一批真实用户消息做上下文,两个 LLM provider 各生成一遍回复,由**固定裁判**
(score 任务链路,默认云端强模型)对照人设打分——量化"本地模型 vs 云端模型"
的人设契合基线差,为后续 LoRA 微调提供对照基准(微调前后同法盲测)。

设计要点:
  - 上下文取自 chat_store 真实历史(最近 N 条 user 消息,各自携带其前文);
  - system_prompt 用**静态人设渲染**(render_system_prompt,含输出契约),
    不注记忆/心情——隔离变量,只测"人设契合"维度;
  - 裁判走 score_service._llm_score(评审 prompt 与线上评分完全一致,
    盲测分数与日常评分同口径可比);
  - 单条失败(限流/超时)计入 errors 不中断整体。

作者: 李文煜
日期: 2026-09-12
"""
import logging

from llm.base import Message
from llm.registry import get_provider
from storage import chat_store

logger = logging.getLogger(__name__)

_MAX_CONTEXTS = 30        # 单次盲测上限(防请求过久)
_HISTORY_WINDOW = 20      # 每条上下文携带的最大前文条数
_SAMPLE_TEXT_MAX = 120    # 返回样本的文本截断(面板展示用)


async def _collect_contexts(redis, oid: str, n: int) -> list[dict]:
    """从真实历史取最近 n 条 user 消息及其前文(转 Message,过滤已删/撤回)"""
    msgs = await chat_store.list_messages(redis, oid, limit=800)
    contexts: list[dict] = []
    history: list[Message] = []
    for m in msgs:
        if m.get("status") in ("deleted", "recalled"):
            continue
        sender = m.get("sender", "")
        content = m.get("content", "") or ""
        if not content:
            continue
        if sender == "user":
            contexts.append({"history": list(history), "user_text": content})
            history.append(Message(role="user", content=content))
        else:
            history.append(Message(role=chat_store._SENDER_TO_ROLE.get(sender, "assistant"),
                                   content=content))
        history = history[-_HISTORY_WINDOW:]
    return contexts[-n:]


def _truncate(text: str, limit: int = _SAMPLE_TEXT_MAX) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


async def benchmark_persona(redis, oid: str, *, provider_a: str, provider_b: str,
                            n: int = 20, judge_provider: str = "") -> dict:
    """人设盲测主入口:A/B 两 provider 对同批上下文生成回复,固定裁判打分对比。
    返回 {n, a: {provider, avg, count, errors}, b: {...}, judge, samples: [...]}。"""
    from takeover.service import _resolve_persona
    from persona.renderer import render_system_prompt
    from score.service import _llm_score

    n = max(1, min(int(n or 20), _MAX_CONTEXTS))
    card = await _resolve_persona(redis, oid)
    system_prompt = render_system_prompt(card)   # 静态人设(含输出契约),不注记忆/心情
    contexts = await _collect_contexts(redis, oid, n)
    if not contexts:
        return {"n": 0, "error": "no_contexts", "message": "该会话无可用用户消息作盲测上下文"}

    pa = get_provider(provider_a)
    pb = get_provider(provider_b)

    async def _gen(provider, ctx) -> str:
        messages = ([Message(role="system", content=system_prompt)]
                    + ctx["history"] + [Message(role="user", content=ctx["user_text"])])
        resp = await provider.chat(messages)
        return resp.text or ""

    result_a = {"provider": provider_a, "scores": [], "errors": 0}
    result_b = {"provider": provider_b, "scores": [], "errors": 0}
    samples = []
    for i, ctx in enumerate(contexts):
        sample = {"user": _truncate(ctx["user_text"])}
        for tag, prov_res, provider in (("a", result_a, pa), ("b", result_b, pb)):
            try:
                reply = await _gen(provider, ctx)
                judged = await _llm_score(reply, card, judge_provider, "")
                if judged is None:
                    prov_res["errors"] += 1
                    sample[tag] = {"reply": _truncate(reply), "score": None}
                else:
                    score, _reason = judged
                    prov_res["scores"].append(score)
                    sample[tag] = {"reply": _truncate(reply), "score": score}
            except Exception as e:
                prov_res["errors"] += 1
                sample[tag] = {"reply": f"<生成失败: {e}>", "score": None}
                logger.warning("盲测 %s 第 %d 条失败: %s", tag, i + 1, e)
        samples.append(sample)

    for r in (result_a, result_b):
        scores = r.pop("scores")
        r["count"] = len(scores)
        r["avg"] = round(sum(scores) / len(scores), 1) if scores else None
    return {"n": len(contexts), "a": result_a, "b": result_b,
            "judge": judge_provider or "score 任务默认链路", "samples": samples}
