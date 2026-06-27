"""
M2 测试公共夹具:独立 fakeredis 实例 + mock LLM provider。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 创建 m2 conftest:fake_redis(独立实例,mood/chat_store 直传)+ mock_provider(记录调用)
"""
import pytest
import fakeredis

from llm.base import LLMProvider, Delta, LLMResponse


@pytest.fixture
def fake_redis():
    """独立 fakeredis 实例(每个测试独立,decode_responses=True)。
    mood/chat_store 测试直接传它;pipeline/debounce 测试再 monkeypatch 注入 redis_client._redis。"""
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield fake


class _MockProvider(LLMProvider):
    """mock LLM provider:stream_chat/chat 产固定文本,记录调用次数与入参 messages。
    用于验证 pipeline 全链路而无需真实 LLM key。"""
    name = "mock"

    def __init__(self, text: str = "mock-reply"):
        self.text = text
        self.call_count = 0
        self.last_messages: list | None = None

    async def chat(self, messages, model="", **opts) -> LLMResponse:
        self.call_count += 1
        self.last_messages = messages
        return LLMResponse(text=self.text)

    async def stream_chat(self, messages, model="", **opts):
        self.call_count += 1
        self.last_messages = messages
        yield Delta(text=self.text)


@pytest.fixture
def mock_provider():
    return _MockProvider()
