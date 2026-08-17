"""
M3 测试公共夹具:fakeredis + 可控 mock LLM provider(评分 JSON / 反推字段 JSON)。
复用根 conftest 的 _no_real_llm(autouse 清空 key);m3 测试显式 monkeypatch key +
get_provider 注入 mock,精确控制 LLM 产出。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 创建 m3 conftest:fake_redis(独立实例)+ _ScriptProvider(chat 返预设文本)+ make_provider 构造器
"""
import pytest
import fakeredis

from llm.base import LLMProvider, Delta, LLMResponse


@pytest.fixture
def fake_redis():
    """独立 fakeredis 实例(每个测试独立,decode_responses=True),直传各 service"""
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield fake


class _ScriptProvider(LLMProvider):
    """可控 mock LLM provider:chat 返回预设文本(评分 JSON / 反推字段 JSON),记录调用。
    用于验证评分/反推逻辑而无需真实 LLM key。"""
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
