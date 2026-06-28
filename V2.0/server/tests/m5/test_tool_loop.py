"""
tool-loop 引擎单测:无工具调用直接返 / 调工具后resolve / 达上限 / 未知工具容错 / 工具异常容错。

作者: 李文煜
日期: 2026-06-28
"""
import json

from llm.base import LLMResponse
from tools.base import Tool, ToolRegistry, ToolContext
from pipeline.tool_loop import run_tool_loop


class _NoteTool(Tool):
    name = "note"
    description = "记录一条信息"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    def __init__(self):
        self.received: list[str] = []

    async def execute(self, args, ctx):
        self.received.append(args.get("text", ""))
        return f"已记录:{args.get('text', '')}"


class _BoomTool(Tool):
    name = "boom"
    description = "执行必崩"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, args, ctx):
        raise RuntimeError("故意崩溃")


async def test_no_tool_calls_returns_directly(make_provider):
    """LLM 不调工具 → 直接返回文本"""
    p = make_provider([LLMResponse(text="你好呀")])
    out = await run_tool_loop(p, "sys", "嗨", [], ToolRegistry(), ToolContext(), model="m")
    assert out == "你好呀"


async def test_calls_tool_then_resolves(make_provider):
    """LLM 先调工具(带 arguments)→ 看到结果 → 产出最终回复"""
    reg = ToolRegistry()
    note = _NoteTool()
    reg.register(note)
    p = make_provider([
        LLMResponse(text="", tool_calls=[{
            "id": "c1", "name": "note",
            "arguments": json.dumps({"text": "用户喜欢猫"}, ensure_ascii=False),
        }]),
        LLMResponse(text="好的,我记住了你喜欢猫"),
    ])
    out = await run_tool_loop(p, "sys", "记一下我喜欢猫", [], reg, ToolContext(), model="m")
    assert out == "好的,我记住了你喜欢猫"
    assert note.received == ["用户喜欢猫"]


async def test_max_iterations_cap(make_provider):
    """LLM 每轮都调工具(死循环)→ 达上限返回提示"""
    reg = ToolRegistry()
    reg.register(_NoteTool())
    p = make_provider([
        LLMResponse(text="", tool_calls=[{"id": f"c{i}", "name": "note", "arguments": "{}"}])
        for i in range(10)
    ])
    out = await run_tool_loop(p, "sys", "x", [], reg, ToolContext(), model="m", max_iterations=3)
    assert "上限" in out


async def test_unknown_tool_handled(make_provider):
    """未知工具不崩,回填提示后 LLM 继续产出回复"""
    p = make_provider([
        LLMResponse(text="", tool_calls=[{"id": "c1", "name": "ghost", "arguments": "{}"}]),
        LLMResponse(text="好的"),
    ])
    out = await run_tool_loop(p, "sys", "x", [], ToolRegistry(), ToolContext(), model="m")
    assert out == "好的"


async def test_tool_exception_isolated(make_provider):
    """工具执行抛异常 → 回填错误信息,不中断循环"""
    reg = ToolRegistry()
    reg.register(_BoomTool())
    p = make_provider([
        LLMResponse(text="", tool_calls=[{"id": "c1", "name": "boom", "arguments": "{}"}]),
        LLMResponse(text="抱歉出错了"),
    ])
    out = await run_tool_loop(p, "sys", "x", [], reg, ToolContext(), model="m")
    assert out == "抱歉出错了"
