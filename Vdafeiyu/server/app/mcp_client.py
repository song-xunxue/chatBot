"""
MCP client(M5)
连外部 MCP server(stdio/sse),discover tools 注册到 ToolRegistry,转发 tool-loop 调用。
借鉴 AstrBot MCP 集成(docs/01 §6)。无 server 配置时降级(只用自研工具)。

config.mcp_servers(JSON 字符串):[{name, transport:"stdio"|"sse", command, args | url}, ...]
stdio 启动子进程 server(command+args);sse 连远程 server(url)。

2026-11-10 重构(跨 task 生命周期修复):
  旧版 AsyncExitStack 在 connect_all 的 task 里 enter stdio/sse 上下文,而 call_tool 来自
  tool-loop 的其他 task——anyio 的 cancel scope/task group 必须同一 task 内 enter/exit,
  跨 task 调用会炸 "Attempted to exit cancel scope in a different task"。
  新版每个 server 配一个专属 owner task:_run 内 enter 上下文 + initialize,之后所有
  session 操作(list/call/close)经 asyncio.Queue 回 owner task 串行执行;调用方 await 的
  只是普通 Future,不再跨 anyio 作用域。停机经哨兵消息让 owner 在自己 task 里正常退上下文。

  Windows stdio 垫片:npm 系 CLI(npx/npm)在 Windows 是 .cmd 批处理垫片,子进程
  shell=False 直接 spawn 裸名/直接 .cmd 都不可靠——探测到即自动 cmd /c 包裹(配置写
  "command":"npx" 即可,无需手写 ["cmd","/c","npx",...])。

日期: 2026-06-28

2026-06-28
变更说明:
  1. M5 新建 MCP client:MCPClient(AsyncExitStack 管理多 server 生命周期)+ _MCPRemoteTool 适配器
     + parse_mcp_servers(JSON 解析)。连接失败隔离(单 server 异常不影响其他)

2026-11-10
变更说明:
  1. AsyncExitStack → 每 server 专属 owner task + 队列转发(修跨 task cancel scope 崩溃)
  2. stdio Windows .cmd 垫片自动 cmd /c 包裹(支持 npx/npm 裸名配置)
  3. close_all 经哨兵停机;_MCPRemoteTool 对外接口不变
"""
import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

from tools.base import Tool

logger = logging.getLogger(__name__)

# Windows 下需要 cmd /c 包裹的裸名 CLI(npm 系垫片是 .cmd 批处理,不能直接 spawn)
_WIN_CMD_SHIMS = {"npx", "npm", "pnpm", "yarn", "tsc", "ng"}


def _resolve_stdio_command(command: str, args: list) -> tuple[str, list]:
    """Windows .cmd 垫片适配:裸名 npm 系 CLI / .cmd|.bat 文件 → cmd /c 包裹,其余原样返回"""
    if sys.platform != "win32":
        return command, args
    p = Path(command)
    suffix = p.suffix.lower()
    bare = p.name.lower()
    need_wrap = suffix in {".cmd", ".bat"} or bare in _WIN_CMD_SHIMS
    if not need_wrap and suffix == "" and shutil.which(f"{command}.cmd"):
        need_wrap = True   # 裸名但存在同名 .cmd 垫片(如自定义目录下的 npx)
    if need_wrap:
        return "cmd", ["/c", command, *args]
    return command, args


class _ServerConnection:
    """单 server 连接:专属 owner task 持有 session(anyio 上下文同 task enter/exit)。

    其他 task 经 _submit 投递调用 → owner 串行执行 → Future 回传结果。
    """

    def __init__(self, name: str, ctx_factory):
        self.name = name
        self._ctx_factory = ctx_factory     # () -> async ctx mgr,产出 (read, write);每次调用新建
        self._calls: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._closed = False

    async def _run(self, ready: asyncio.Future) -> None:
        """owner task:enter 连接上下文 → initialize → 循环消费调用队列(全在本 task)"""
        from mcp import ClientSession
        try:
            async with self._ctx_factory() as streams:
                read, write = streams
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    ready.set_result(None)
                    while not self._closed:
                        item = await self._calls.get()
                        if item is None:            # 停机哨兵 → 退出 async with(同 task exit ✓)
                            break
                        kind, fut, payload = item
                        try:
                            if kind == "list":
                                fut.set_result(await session.list_tools())
                            else:
                                fut.set_result(await session.call_tool(*payload))
                        except Exception as e:      # 单次调用失败不炸 owner(隔离给调用方)
                            fut.set_exception(e)
        except Exception as e:
            if not ready.done():
                ready.set_exception(e)              # 启动阶段失败 → connect_all 隔离处理
            else:
                logger.warning("MCP server %s 连接循环退出: %s", self.name, e)
        # 排空遗留调用(连断后到达的请求全部明确失败,不留悬挂 Future)
        while not self._calls.empty():
            item = self._calls.get_nowait()
            if item is not None and not item[1].done():
                item[1].set_exception(RuntimeError(f"MCP server {self.name} 已断开"))

    async def start(self) -> None:
        """拉起 owner task 并等待 initialize 完成(失败抛原异常,由 connect_all 隔离)"""
        ready = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(self._run(ready), name=f"mcp-owner-{self.name}")
        await ready

    async def _submit(self, kind: str, payload: tuple):
        if self._closed or self._task is None or self._task.done():
            raise RuntimeError(f"MCP server {self.name} 未连接")
        fut = asyncio.get_running_loop().create_future()
        await self._calls.put((kind, fut, payload))
        return await fut

    async def list_tools(self):
        return await self._submit("list", ())

    async def call_tool(self, tool_name: str, args: dict):
        return await self._submit("call", (tool_name, args))

    async def stop(self) -> None:
        """停机:哨兵让 owner 在自己 task 里退上下文;超时兜底 cancel(上下文仍在同 task 退出)"""
        self._closed = True
        if self._task is None:
            return
        await self._calls.put(None)
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=5)
        except (asyncio.TimeoutError, Exception):
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass


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
    """MCP 多 server 客户端:每 server 一个 owner task 管理连接生命周期(2026-11-10 重构)"""

    def __init__(self):
        self._conns: dict = {}         # server_name -> _ServerConnection
        self._tool_owner: dict = {}    # tool_name -> server_name(重名后注册者覆盖)

    async def connect_all(self, servers: list[dict], registry) -> int:
        """连所有 MCP server,discover tools 注册到 registry。返回成功连接 server 数。
        单 server 连接失败隔离(记日志,不影响其他)。"""
        connected = 0
        for cfg in servers:
            name = cfg.get("name") or cfg.get("command") or "mcp"
            try:
                if cfg.get("transport") == "sse":
                    from mcp.client.sse import sse_client
                    url = cfg["url"]
                    ctx_factory = lambda: sse_client(url)          # noqa: E731 每次进上下文新建 cm(cm 只能 enter 一次)
                else:   # stdio(默认)
                    from mcp.client.stdio import stdio_client, StdioServerParameters
                    command, args = _resolve_stdio_command(
                        cfg["command"], list(cfg.get("args", []) or []))
                    params = StdioServerParameters(command=command, args=args, env=cfg.get("env"))
                    ctx_factory = lambda p=params: stdio_client(p)  # noqa: E731
                conn = _ServerConnection(name, ctx_factory)
                await conn.start()
                self._conns[name] = conn
                tools = await conn.list_tools()
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
        conn = self._conns.get(server_name)
        if conn is None:
            return f"[MCP server {server_name} 未连接]"
        try:
            result = await conn.call_tool(tool_name, args)
        except Exception as e:
            logger.warning("MCP 调用失败 %s/%s: %s", server_name, tool_name, e)
            return f"[MCP 调用失败: {e}]"
        texts = [getattr(c, "text", "") for c in (result.content or [])]
        return "\n".join(t for t in texts if t)

    async def close_all(self) -> None:
        """关闭所有连接(各 owner task 在自己的 task 里逆序退上下文)"""
        for conn in list(self._conns.values()):
            try:
                await conn.stop()
            except Exception:
                logger.warning("MCP server %s close 异常(忽略)", conn.name, exc_info=True)
        self._conns.clear()


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
