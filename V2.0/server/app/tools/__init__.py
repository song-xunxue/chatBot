"""
工具系统模块(M5)
Tool/ToolRegistry/ToolContext + 自研工具 + 全局 registry 单例。
对应 docs/01 §6(tool-loop 自研工具)+ docs/04 §8(@llm_tool→tool-loop 注册)。

作者: 李文煜
日期: 2026-06-28
"""
from tools.base import Tool, ToolRegistry, ToolContext, get_tool_registry
from tools.builtin import register_builtin_tools

__all__ = ["Tool", "ToolRegistry", "ToolContext", "get_tool_registry", "register_builtin_tools"]
