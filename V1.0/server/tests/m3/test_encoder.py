"""
记忆编码器单元测试（mock LLM）
验证 summarize/reflect/extract_facts/_parse_facts/heuristic 降级/clamp

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.4 覆盖 encoder 全部函数
"""
from unittest.mock import AsyncMock

from memory import encoder
from llm.base import LLMResponse, Message


async def test_summarize_with_llm():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(text="摘要结果")
    s = await encoder.summarize([Message(role="user", content="hi")], llm)
    assert s == "摘要结果"


async def test_summarize_no_llm_heuristic():
    s = await encoder.summarize(
        [Message(role="user", content="你好"), Message(role="assistant", content="嗨")], None)
    assert "你好" in s


async def test_reflect_with_llm():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(text="用户爱聊技术")
    r = await encoder.reflect(["摘要1", "摘要2"], llm)
    assert r == "用户爱聊技术"


async def test_reflect_empty_input_returns_empty():
    r = await encoder.reflect([], AsyncMock())
    assert r == ""


async def test_extract_facts_parse_json():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='前面文字[{"content":"喜欢猫","importance":0.9,"emotion":0.5,"category":"preference"}]后面')
    facts = await encoder.extract_facts("我喜欢猫", "好", llm)
    assert len(facts) == 1
    assert facts[0]["content"] == "喜欢猫"
    assert facts[0]["importance"] == 0.9
    assert facts[0]["category"] == "preference"


async def test_extract_facts_no_llm_returns_empty():
    assert await encoder.extract_facts("x", "y", None) == []


async def test_extract_facts_invalid_json_returns_empty():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(text="不是JSON")
    assert await encoder.extract_facts("x", "y", llm) == []


async def test_extract_facts_clamps_out_of_range():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='[{"content":"x","importance":5.0,"emotion":-1,"category":"fact"}]')
    facts = await encoder.extract_facts("x", "y", llm)
    assert facts[0]["importance"] == 1.0  # clamp 到 [0,1]
    assert facts[0]["emotion"] == 0.0


async def test_extract_facts_invalid_category_falls_back():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='[{"content":"x","importance":0.5,"category":"未知类别"}]')
    facts = await encoder.extract_facts("x", "y", llm)
    assert facts[0]["category"] == "fact"  # 非法类别回退 fact
