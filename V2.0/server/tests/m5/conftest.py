"""
M5 测试公共夹具:fakeredis + 可控 mock LLM provider(chat_with_tools 按预设序列返回 tool_calls/text)。
复用根 conftest 的 _no_real_llm / _disable_tool_loop(autouse)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M5 创建 m5 conftest:fake_redis + _ToolProvider(chat_with_tools 预设响应序列)
"""
import pytest
import fakeredis

from llm.base import LLMProvider, Delta, LLMResponse


@pytest.fixture
def fake_redis():
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield fake


class _ToolProvider(LLMProvider):
    """可控 mock LLM provider:chat_with_tools 按预设序列返回 LLMResponse(tool_calls/text)。
    responses 为 list[LLMResponse],每次调用 pop(0)。记录调用入参供断言。"""
    name = "mock"

    def __init__(self, responses: list[LLMResponse] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    async def chat(self, messages, model="", **opts):
        self.calls.append({"messages": messages})
        return self._next()

    async def chat_with_tools(self, messages, model="", tools=None, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools})
        return self._next()

    async def stream_chat(self, messages, model="", **opts):
        yield Delta(text=self._next().text)

    def _next(self) -> LLMResponse:
        return self.responses.pop(0) if self.responses else LLMResponse(text="(无预设响应)")


@pytest.fixture
def make_provider():
    """返回构造器:make_provider(responses_list) → _ToolProvider"""
    return _ToolProvider
