"""
MCP client(M5)
连外部 MCP server(stdio/sse),discover tools 注册到 ToolRegistry,转发 tool-loop 调用。
借鉴 AstrBot MCP 集成(docs/01 §6)。无 server 配置时降级(只用自研工具)。

config.mcp_servers(JSON 字符串):[{name, transport:"stdio"|"sse", command, args | url}, ...]
stdio 启动子进程 server(command+args);sse 连远程 server(url)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M5 新建 MCP client:MCPClient(AsyncExitStack 管理多 server 生命周期)+ _MCPRemoteTool 适配器
     + parse_mcp_servers(JSON 解析)。连接失败隔离(单 server 异常不影响其他)
"""
import json
import logging
from contextlib import AsyncExitStack

from tools.base import Tool

logger = logging.getLogger(__name__)


class _MCPRemoteTool(Tool):
    """MCP 远程工具的 Tool 适配器:execute 转发给 MCPClient.call"""

    def __init__(self, server_name: str, name: str, description: str,
                 input_schema: dict, manager: "MCPClient"):
        self.server_name = server_name
        self.name = name
        self.description = description or ""
        self.parameters = input_schema or {}
        self.manager = manager

    async def execute(self, args: dict, ctx) -> str:
        return await self.manager.call(self.server_name, self.name, args)


class MCPClient:
    """MCP 多 server 客户端:AsyncExitStack 统一管理各 server 连接生命周期"""

    def __init__(self):
        self._stack = AsyncExitStack()
        self._sessions: dict = {}      # server_name -> ClientSession
        self._tool_owner: dict = {}    # tool_name -> server_name(重名后注册者覆盖)

    async def connect_all(self, servers: list[dict], registry) -> int:
        """连所有 MCP server,discover tools 注册到 registry。返回成功连接 server 数。
        单 server 连接失败隔离(记日志,不影响其他)。"""
        from mcp import ClientSession
        connected = 0
        for cfg in servers:
            name = cfg.get("name") or cfg.get("command") or "mcp"
            try:
                if cfg.get("transport") == "sse":
                    from mcp.client.sse import sse_client
                    read, write = await self._stack.enter_async_context(sse_client(cfg["url"]))
                else:   # stdio(默认)
                    from mcp.client.stdio import stdio_client, StdioServerParameters
                    params = StdioServerParameters(
                        command=cfg["command"], args=cfg.get("args", []) or [],
                        env=cfg.get("env"))
                    read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[name] = session
                tools = await session.list_tools()
                for t in tools.tools:
                    registry.register(_MCPRemoteTool(name, t.name, t.description, t.inputSchema, self))
                    self._tool_owner[t.name] = name
                connected += 1
                logger.info("MCP server %s connected, %d tools registered", name, len(tools.tools))
            except Exception as e:
                logger.warning("MCP server %s connect failed, isolated: %s", name, e)
        return connected

    async def call(self, server_name: str, tool_name: str, args: dict) -> str:
        """转发工具调用到对应 MCP server,返回文本结果"""
        session = self._sessions.get(server_name)
        if session is None:
            return f"[MCP server {server_name} 未连接]"
        result = await session.call_tool(tool_name, args)
        texts = [getattr(c, "text", "") for c in (result.content or [])]
        return "\n".join(t for t in texts if t)

    async def close_all(self) -> None:
        """关闭所有连接(AsyncExitStack 逆序退出各 context)"""
        await self._stack.aclose()


def parse_mcp_servers(json_str: str) -> list[dict]:
    """解析 config.mcp_servers(JSON 字符串)→ list[dict];空/非法返回 [](降级不连)"""
    if not json_str or not json_str.strip():
        return []
    try:
        data = json.loads(json_str)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError as e:
        logger.warning("mcp_servers JSON 解析失败,跳过 MCP: %s", e)
        return []
