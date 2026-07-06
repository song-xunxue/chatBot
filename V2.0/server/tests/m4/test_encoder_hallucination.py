"""
记忆编码幻觉防护单测(2026-07-06 B-3):
验证 extract_facts / summarize 的 prompt 含防幻觉铁律(只信用户陈述,角色回复里未确认的
承诺/虚构不抽),从 prompt 构造层防"椰子鸡变记忆"类幻觉固化。
LLM 真实效果靠集成测/线上观察;单测验证 prompt 被正确注入约束 + 第一人称视角铁律(07-06 既有)不丢。

作者: 李文煜
日期: 2026-07-06
"""
from types import SimpleNamespace

from llm.base import Message
from memory import encoder


class _CaptureLLM:
    """mock LLM:捕获传入 prompt,返回空 JSON(让 extract_facts/summarize 不报错即可)"""

    def __init__(self):
        self.captured = ""

    async def chat(self, messages, model=""):
        self.captured = messages[0].content
        return SimpleNamespace(text="[]")


async def test_extract_facts_prompt_has_antihallucination_rule():
    """B-3:extract_facts prompt 须含防幻觉铁律,且原料(user/reply)与第一人称视角铁律不丢"""
    llm = _CaptureLLM()
    await encoder.extract_facts("我今天买了本漫画", "下周带你去吃椰子鸡好不好", llm)
    p = llm.captured
    # 防幻觉铁律关键词
    assert "防幻觉" in p
    assert "用户" in p and "确认" in p
    # 椰子鸡作为反例写进 prompt(帮 LLM 识别虚构承诺)
    assert "椰子鸡" in p
    # 原料(user_text + reply_text)均喂入
    assert "漫画" in p
    # 第一人称视角铁律(07-06 既有)保留
    assert "第一人称" in p


async def test_summarize_prompt_has_antihallucination_rule():
    """B-3:summarize prompt 须含防幻觉约束(assistant 未确认的承诺不写进概括)"""
    llm = _CaptureLLM()
    msgs = [Message(role="user", content="今天加班好累"),
            Message(role="assistant", content="下周请你吃大餐补补")]
    await encoder.summarize(msgs, llm)
    p = llm.captured
    assert "user" in p
    assert "未确认" in p or "虚构" in p or "幻觉" in p
