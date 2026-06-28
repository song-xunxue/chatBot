"""
工具系统基类(M5)
Tool(工具抽象:name/description/parameters JSON schema/execute)+ ToolRegistry(注册/查询/
导出 OpenAI tools 格式/统一调用)+ ToolContext(执行上下文:redis/object_id)。
供 tool-loop 引擎与 MCP client 注册的工具统一调度,LLM 经 function calling 决策调用。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M5 新建 tools 基类:Tool/ToolRegistry/ToolContext + 全局 registry 单例
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


class ToolContext:
    """工具执行上下文:注入工具所需的依赖(自研工具用 redis/object_id)"""
    def __init__(self, redis: "Redis | None" = None, object_id: str = ""):
        self.redis = redis
        self.object_id = object_id


class Tool(ABC):
    """工具抽象:子类设 name/description/parameters(JSON schema),实现 execute"""
    name: str = ""
    description: str = ""
    parameters: dict = {}   # JSON schema(空则 {type:object,properties:{}})

    @abstractmethod
    async def execute(self, args: dict, ctx: ToolContext) -> str:
        """执行工具,返回文本结果(回填给 LLM)"""
        ...

    def to_openai(self) -> dict:
        """导出 OpenAI function calling 工具 schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


class ToolRegistry:
    """工具注册表:注册/查询/导出 OpenAI tools/统一调用"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具(同名覆盖)"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def openai_tools(self) -> list[dict]:
        """导出全部工具的 OpenAI schema(供 provider chat_with_tools 的 tools 参数)"""
        return [t.to_openai() for t in self._tools.values()]

    async def call(self, name: str, args: dict, ctx: ToolContext) -> str:
        """按名调用工具;未知工具返回提示(不抛,tool-loop 容错)"""
        tool = self.get(name)
        if tool is None:
            return f"[未知工具: {name}]"
        return await tool.execute(args, ctx)


# 全局单例(main lifespan 注册自研工具 + MCP discover 后注册)
_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _registry
