"""
M4 测试公共夹具:fakeredis + 可控 mock LLM provider(consolidate/编码用)。
复用根 conftest 的 _no_real_llm(autouse 清空 key)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M4 创建 m4 conftest:fake_redis(独立实例)+ _ScriptProvider(chat 返预设文本)+ make_provider
"""
import pytest
import fakeredis

from llm.base import LLMProvider, Delta, LLMResponse


@pytest.fixture
def fake_redis():
    """独立 fakeredis 实例(每个测试独立,decode_responses=True),直传各 service/store"""
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield fake


class _ScriptProvider(LLMProvider):
    """可控 mock LLM provider:chat 返回预设文本(consolidate JSON / 编码),记录调用"""
    name = "mock"

    def __init__(self, text: str = ""):
        self.text = text
        self.call_count = 0
        self.last_messages = None

    async def chat(self, messages, model="", **opts) -> LLMResponse:
        self.call_count += 1
        self.last_messages = messages
        return LLMResponse(text=self.text)

    async def stream_chat(self, messages, model="", **opts):
        self.call_count += 1
        self.last_messages = messages
        yield Delta(text=self.text)


@pytest.fixture
def make_provider():
    """返回构造器:make_provider(text) → _ScriptProvider(text)"""
    return _ScriptProvider
