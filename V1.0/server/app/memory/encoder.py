"""
记忆编码管线
summarize（对话摘要）+ reflect（反思归纳）+ extract_facts（事实抽取带 importance/emotion/category）。
调用 LLMProvider；无 LLM 或调用失败时降级（摘要用启发式，事实抽取返回空）。
对应 docs/06 §4、docs/09 §4.3。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.4 创建编码管线：summarize/reflect/extract_facts + JSON 解析与降级
"""
import json
import logging
import re

from llm.base import LLMProvider, Message

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = ("fact", "preference", "relationship", "event", "personality")


async def summarize(messages: list, llm: LLMProvider | None, model: str = "") -> str:
    """把若干轮对话摘要为一句/段（写入 Episodic 层）"""
    if not llm:
        return _heuristic_summary(messages)
    dialog = "\n".join(f"{m.role}: {m.content}" for m in messages[-6:])  # 最近几轮，控 token
    prompt = ("请用一两句中文概括以下对话的关键信息（事实/偏好/事件），"
              "只输出概括，不要寒暄：\n" + dialog)
    try:
        resp = await llm.chat([Message(role="user", content=prompt)], model=model)
        return resp.text.strip()
    except Exception as e:
        logger.warning("summarize 调用失败，降级启发式: %s", e)
        return _heuristic_summary(messages)


async def reflect(episodic_summaries: list[str], llm: LLMProvider | None,
                  model: str = "") -> str:
    """把若干条 Episodic 摘要归纳为更高层反思（跨对话规律）"""
    if not llm or not episodic_summaries:
        return ""
    joined = "\n".join(f"- {s}" for s in episodic_summaries)
    prompt = "请根据以下近期对话摘要，提炼一两句关于用户的高层规律/偏好/关系结论：\n" + joined
    try:
        resp = await llm.chat([Message(role="user", content=prompt)], model=model)
        return resp.text.strip()
    except Exception as e:
        logger.warning("reflect 调用失败: %s", e)
        return ""


async def extract_facts(user_text: str, reply_text: str, llm: LLMProvider | None,
                        model: str = "") -> list[dict]:
    """从一轮对话抽取值得长期记住的事实，带 importance/emotion/category。
    返回 [{content, importance, emotion, category}, ...]；无 LLM 或失败返回空"""
    if not llm:
        return []
    prompt = (
        "从以下用户与助手的对话中，抽取值得长期记住的关于用户的事实/偏好/关系/事件（没有则返回空数组 []）。\n"
        f"用户: {user_text}\n助手: {reply_text}\n"
        "严格只输出一个 JSON 数组，每个元素形如 "
        '{"content": str, "importance": 0-1, "emotion": 0-1, '
        '"category": "fact|preference|relationship|event|personality"}，不要解释。'
    )
    try:
        resp = await llm.chat([Message(role="user", content=prompt)], model=model)
        return _parse_facts(resp.text)
    except Exception as e:
        logger.warning("extract_facts 调用失败: %s", e)
        return []


def _parse_facts(text: str) -> list[dict]:
    """从 LLM 输出解析 JSON 事实数组。
    用 raw_decode 从每个 '[' 尝试解析首个完整 JSON 数组，容忍前后多余文本与嵌套"""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "[":
            continue
        try:
            arr, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        facts = []
        for f in arr:
            if not isinstance(f, dict) or not f.get("content"):
                continue
            cat = f.get("category", "fact")
            facts.append({
                "content": str(f["content"]),
                "importance": _clamp(float(f.get("importance", 0.5))),
                "emotion": _clamp(float(f.get("emotion", 0.0))),
                "category": cat if cat in _VALID_CATEGORIES else "fact",
            })
        return facts
    return []


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _heuristic_summary(messages: list) -> str:
    """无 LLM 时的降级摘要：拼接最近几条用户消息"""
    user_msgs = [m.content for m in messages if m.role == "user"][-3:]
    return "用户提到：" + "；".join(user_msgs) if user_msgs else ""
