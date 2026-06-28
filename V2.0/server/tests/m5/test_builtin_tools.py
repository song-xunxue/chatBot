"""
自研工具单测:get_persona(绑定/未绑定)+ write_memory(写入/空内容/类别)+
web_search(mock DuckDuckGo JSON)+ register_builtin_tools 全注册。

作者: 李文煜
日期: 2026-06-28
"""
import json

import httpx

from tools.builtin import GetPersonaTool, WriteMemoryTool, WebSearchTool, register_builtin_tools
from tools.base import ToolContext, ToolRegistry
from persona.store import set_persona, bind_object_persona
from persona.models import PersonaCard


async def test_get_persona_bound(fake_redis):
    card = PersonaCard(id="p1", name="小晴", creator_notes="我是小晴,性格温柔")
    await set_persona(fake_redis, card)
    await bind_object_persona(fake_redis, "u1", "p1")
    out = await GetPersonaTool().execute({}, ToolContext(redis=fake_redis, object_id="u1"))
    assert "小晴" in out


async def test_get_persona_returns_string(fake_redis):
    """未绑定且默认人设未 seed → 仍返回字符串(不抛)"""
    out = await GetPersonaTool().execute({}, ToolContext(redis=fake_redis, object_id="ghost"))
    assert isinstance(out, str)


async def test_write_memory_writes(fake_redis):
    from memory import store
    out = await WriteMemoryTool().execute(
        {"content": "用户喜欢猫", "category": "preference", "importance": 0.8},
        ToolContext(redis=fake_redis, object_id="u1"))
    assert "已写入" in out
    items = await store.get_all_long_term(fake_redis, "u1")
    assert any("猫" in m.content for m in items)


async def test_write_memory_empty_content(fake_redis):
    out = await WriteMemoryTool().execute({"content": ""}, ToolContext(redis=fake_redis, object_id="u1"))
    assert "空" in out


class _DDGFake:
    """模拟 DuckDuckGo Instant Answer API 响应(httpx.AsyncClient 替身)"""
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        class _Resp:
            def json(self):
                return {"AbstractText": "Python是编程语言", "Heading": "Python",
                        "AbstractURL": "http://x", "RelatedTopics": [{"Text": "相关:蛇"}]}
        return _Resp()


async def test_web_search_parses_ddg(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _DDGFake)
    out = await WebSearchTool().execute({"query": "Python"}, ToolContext())
    data = json.loads(out)
    assert data[0]["text"] == "Python是编程语言"


async def test_web_search_empty_query():
    out = await WebSearchTool().execute({"query": ""}, ToolContext())
    assert "空" in out


def test_register_builtin_all():
    r = ToolRegistry()
    register_builtin_tools(r)
    names = {t.name for t in r.all()}
    assert {"get_persona", "write_memory", "reverse_infer_trigger", "web_search"} <= names
