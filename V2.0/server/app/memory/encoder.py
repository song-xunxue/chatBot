"""
记忆编码管线
summarize(对话摘要) + reflect(反思归纳) + extract_facts(事实抽取带 importance/emotion/category)。
调用 LLMProvider;无 LLM 或调用失败时降级(摘要用启发式,事实抽取返回空)。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植编码管线到 V2.0(零业务改动;summarize/reflect/extract_facts + JSON 解析降级)
"""
import logging
import re

from llm.base import LLMProvider, Message

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = ("fact", "preference", "relationship", "event", "personality")


async def summarize(messages: list, llm: LLMProvider | None, model: str = "") -> str:
    """把若干轮对话摘要为一句/段(写入 Episodic 层)"""
    if not llm:
        return _heuristic_summary(messages)
    dialog = "\n".join(f"{m.role}: {m.content}" for m in messages[-6:])  # 最近几轮,控 token
    prompt = ("请用一两句中文概括以下对话的关键信息(事实/偏好/事件),"
              "只输出概括,不要寒暄:\n" + dialog)
    try:
        resp = await llm.chat([Message(role="user", content=prompt)], model=model)
        return resp.text.strip()
    except Exception as e:
        logger.warning("summarize 调用失败,降级启发式: %s", e)
        return _heuristic_summary(messages)


async def reflect(episodic_summaries: list[str], llm: LLMProvider | None,
                  model: str = "") -> str:
    """把若干条 Episodic 摘要归纳为更高层反思(跨对话规律)"""
    if not llm or not episodic_summaries:
        return ""
    joined = "\n".join(f"- {s}" for s in episodic_summaries)
    prompt = "请根据以下近期对话摘要,提炼一两句关于用户的高层规律/偏好/关系结论:\n" + joined
    try:
        resp = await llm.chat([Message(role="user", content=prompt)], model=model)
        return resp.text.strip()
    except Exception as e:
        logger.warning("reflect 调用失败: %s", e)
        return ""


async def extract_facts(user_text: str, reply_text: str, llm: LLMProvider | None,
                        model: str = "") -> list[dict]:
    """从一轮对话抽取值得长期记住的事实,带 importance/emotion/category。
    返回 [{content, importance, emotion, category}, ...];无 LLM 或失败返回空"""
    if not llm:
        return []
    prompt = (
        "你在为【角色本人】整理长期记忆。请以角色第一人称('我'指角色自己)视角,"
        "从以下对话中抽取角色值得长期记住的认知——关于【用户】(对方)的特点/偏好/事件、"
        "角色与用户的关系、以及角色自身的事(如角色的名字/身份/喜好)。\n"
        "关键:严格区分'我'(角色)与'用户'(对方),切勿把角色自己的名字或特征记成用户的。"
        "content 用角色口吻,例如'我叫清浔''用户希望被称为煜''用户喜欢动漫''我和用户是同学'。\n"
        f"用户: {user_text}\n角色(我): {reply_text}\n"
        "严格只输出一个 JSON 数组,每个元素形如 "
        '{"content": str, "importance": 0-1, "emotion": 0-1, '
        '"category": "fact|preference|relationship|event|personality"},没有则返回 []。'
    )
    try:
        resp = await llm.chat([Message(role="user", content=prompt)], model=model)
        return _parse_facts(resp.text)
    except Exception as e:
        logger.warning("extract_facts 调用失败: %s", e)
        return []


def _parse_facts(text: str) -> list[dict]:
    """从 LLM 输出解析 JSON 事实数组(首个数组,容忍前后多余文本/嵌套);每元素做结构校验。
    数组提取收口于 llm.json_extract。"""
    from llm.json_extract import extract_json_array
    arr = extract_json_array(text)
    if not arr:
        return []
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


async def consolidate_facts(episodic_summaries: list[str], llm: LLMProvider | None,
                            model: str = "") -> list[dict]:
    """睡眠巩固(M4,借鉴 angel_memory):从情景记忆摘要提炼长期事实。
    返回 [{content, importance, emotion, category}, ...];无 LLM 或失败返回空。"""
    if not llm or not episodic_summaries:
        return []
    joined = "\n".join(f"- {s}" for s in episodic_summaries[-20:])   # 最近 20 条摘要,控 token
    prompt = (
        "你在为【角色本人】整理长期记忆。以下是角色与用户若干段对话的情景摘要。"
        "请以角色第一人称('我'指角色自己)视角,从中提炼角色值得长期记住的认知——"
        "关于用户的特点/偏好、角色与用户的关系、角色自身的事。\n"
        "关键:严格区分'我'(角色)与'用户'(对方),切勿把角色名字/特征记成用户的。"
        "content 用角色口吻(如'我叫清浔''用户喜欢动漫')。\n" + joined +
        "\n严格只输出一个 JSON 数组,每个元素形如 "
        '{"content": str, "importance": 0-1, "emotion": 0-1, '
        '"category": "fact|preference|relationship|event|personality"},没有则返回 []。'
    )
    try:
        resp = await llm.chat([Message(role="user", content=prompt)], model=model)
        return _parse_facts(resp.text)
    except Exception as e:
        logger.warning("consolidate_facts 调用失败: %s", e)
        return []


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _heuristic_summary(messages: list) -> str:
    """无 LLM 时的降级摘要:拼接最近几条用户消息"""
    user_msgs = [m.content for m in messages if m.role == "user"][-3:]
    return "用户提到:" + ";".join(user_msgs) if user_msgs else ""
