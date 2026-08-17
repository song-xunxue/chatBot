"""
tools 基类单测:Tool(to_openai/execute)+ ToolRegistry(register/get/all/openai_tools/call)。

作者: 李文煜
日期: 2026-06-28
"""
from tools.base import Tool, ToolRegistry, ToolContext


class _EchoTool(Tool):
    name = "echo"
    description = "回显输入文本"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    async def execute(self, args, ctx):
        return f"echo:{args.get('text', '')}"


def test_registry_register_and_get():
    r = ToolRegistry()
    r.register(_EchoTool())
    assert r.get("echo") is not None
    assert r.get("nope") is None
    assert len(r.all()) == 1


def test_registry_openai_tools_schema():
    r = ToolRegistry()
    r.register(_EchoTool())
    schema = r.openai_tools()
    assert schema[0]["type"] == "function"
    assert schema[0]["function"]["name"] == "echo"
    assert "text" in schema[0]["function"]["parameters"]["properties"]


async def test_registry_call():
    r = ToolRegistry()
    r.register(_EchoTool())
    out = await r.call("echo", {"text": "hi"}, ToolContext())
    assert out == "echo:hi"


async def test_registry_call_unknown_tool():
    r = ToolRegistry()
    out = await r.call("ghost", {}, ToolContext())
    assert "未知工具" in out
