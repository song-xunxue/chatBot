"""
M8 测试公共夹具:fakeredis + 可控 mock LLM provider(评分 JSON)。
复用根 conftest 的 _qq_secret/_no_real_llm/api_client/qq_http(autouse 注入 QQ MockTransport/清 LLM key);
M8 测试显式 monkeypatch 控制 send_c2c_message 下发分支 + 评分 provider。

作者: 李文煜
日期: 2026-06-30

2026-06-30
变更说明：
  1. M8 创建 m8 conftest:fake_redis(独立实例)+ make_provider(评分 JSON mock LLM)
"""
import pytest
import fakeredis

from llm.base import LLMProvider, Delta, LLMResponse


@pytest.fixture
def fake_redis():
    """独立 fakeredis 实例(每个测试独立,decode_responses=True),直传 store/service 函数"""
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield fake


class _ScriptProvider(LLMProvider):
    """可控 mock LLM provider:chat 返回预设文本(评分 JSON),记录调用。"""
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
