"""
记忆编码管线
summarize(对话摘要) + reflect(反思归纳) + extract_facts(事实抽取带 importance/emotion/category)。
调用 LLMProvider;无 LLM 或调用失败时降级(摘要用启发式,事实抽取返回空)。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植编码管线到 V2.0(零业务改动;summarize/reflect/extract_facts + JSON 解析降级)

2026-07-06
变更说明：
  1. B-3 记忆幻觉防护:extract_facts + summarize prompt 加防幻觉铁律
     (只信用户陈述,角色回复里未确认的承诺/虚构不抽,防"椰子鸡变记忆"类幻觉固化)

2026-07-07
变更说明：
  1. 记忆优化阶段2:新增 extract_facts_batch(多轮批量提取,替每轮单条降 LLM 成本,带防幻觉)
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
    prompt = ("请用一两句中文概括以下对话的关键信息(事实/偏好/事件),只输出概括,不要寒暄。\n"
              "注意:只概括 user 一方明确陈述的事实;assistant 一方的承诺/虚构/假设若 user 未确认,"
              "不要当成事实写进概括(防幻觉固化进情景记忆):\n" + dialog)
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
        "【防幻觉铁律——必须遵守】\n"
        "1. 只把'用户说的话'(user 那行)当作事实来源。角色(我)的回复(reply 那行)里提到的事"
        "——尤其承诺、计划、假设、虚构(例如角色说'下周带你去吃椰子鸡'但用户从没提过椰子鸡)——"
        "若用户没有明确确认,绝对不要抽成记忆:那很可能只是角色随口编的,不是真的事实。\n"
        "2. 区分谁说的:用户亲口陈述的偏好/事件才记;角色回复里的话只在用户本轮或之前确认过时才记。\n"
        "3. 严格区分'我'(角色)与'用户'(对方),切勿把角色名字/特征记成用户的。\n"
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


async def extract_facts_batch(messages: list, llm: LLMProvider | None,
                              model: str = "") -> list[dict]:
    """从最近 N 轮对话批量提取事实(2026-07-07 优化3:替每轮单条 extract_facts,降 LLM 成本)。
    带防幻觉铁律(只信用户陈述,角色虚构承诺不抽)。返回 [{content, importance, emotion, category}]。
    无 LLM/无消息/失败返回空。"""
    if not llm or not messages:
        return []
    # 格式化多轮对话(最近 12 条控 token;user→用户,assistant→角色)
    dialog = "\n".join(
        f"{'用户' if m.role == 'user' else '角色(我)'}: {m.content}"
        for m in messages[-12:] if getattr(m, "content", "")
    )
    if not dialog.strip():
        return []
    prompt = (
        "你在为【角色本人】整理长期记忆。以下是角色与用户最近的若干轮对话。"
        "请以角色第一人称('我'指角色自己)视角,从中抽取角色值得长期记住的认知"
        "——关于用户的特点/偏好/事件、角色与用户的关系、角色自身的事。\n"
        "【防幻觉铁律——必须遵守】\n"
        "1. 只把'用户说的话'当作事实来源。角色(我)的回复里提到的事——尤其承诺、计划、假设、虚构"
        "(例如角色说'下周带你去吃椰子鸡'但用户从没提过)——若用户没有明确确认,绝对不要抽成记忆。\n"
        "2. 用户亲口陈述的偏好/事件才记;角色回复里的话只在用户本轮或之前确认过时才记。\n"
        "3. 严格区分'我'(角色)与'用户'(对方),切勿把角色名字/特征记成用户的。\n"
        "content 用角色口吻(如'我叫清浔''用户喜欢动漫''我和用户是同学')。\n\n"
        f"{dialog}\n\n"
        "严格只输出一个 JSON 数组,每个元素形如 "
        '{"content": str, "importance": 0-1, "emotion": 0-1, '
        '"category": "fact|preference|relationship|event|personality"},没有则返回 []。'
    )
    try:
        resp = await llm.chat([Message(role="user", content=prompt)], model=model)
        return _parse_facts(resp.text)
    except Exception as e:
        logger.warning("extract_facts_batch 调用失败: %s", e)
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
