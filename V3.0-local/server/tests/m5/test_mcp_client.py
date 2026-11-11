"""
MCP client 单测:parse_mcp_servers(JSON 解析/降级)+ _MCPRemoteTool(转发/ schema)+
MCPClient.call(mock 连接转发)+ owner-task 跨 task 调用 + Windows cmd 垫片解析。
不真连外部 server(连接集成留真实验证)。

日期: 2026-06-28

2026-11-10
变更说明:
  1. mock 对象从 _sessions(session)换成 _conns(_ServerConnection);新增 owner-task
     跨 task 调用测试(修 AsyncExitStack 跨 task 崩溃的行为钉子)+ cmd 垫片解析测试
"""
import asyncio
import sys

from mcp_client import (
    parse_mcp_servers, MCPClient, _MCPRemoteTool,
    _ServerConnection, _resolve_stdio_command,
)


def test_parse_mcp_servers_empty_and_invalid():
    assert parse_mcp_servers("") == []
    assert parse_mcp_servers("   ") == []
    assert parse_mcp_servers("not json") == []
    assert parse_mcp_servers('{"not":"list"}') == []   # 非数组


def test_parse_mcp_servers_valid():
    s = parse_mcp_servers(
        '[{"name":"s1","transport":"stdio","command":"python","args":["-m","srv"]},'
        '{"name":"s2","transport":"sse","url":"http://x/sse"}]')
    assert len(s) == 2
    assert s[0]["command"] == "python"
    assert s[1]["transport"] == "sse"


def test_resolve_stdio_command_cmd_shims(monkeypatch):
    """Windows 垫片解析:npx/npm 裸名与 .cmd/.bat → cmd /c 包裹;普通 exe 原样"""
    monkeypatch.setattr(sys, "platform", "win32")
    assert _resolve_stdio_command("npx", ["-y", "srv"]) == ("cmd", ["/c", "npx", "-y", "srv"])
    assert _resolve_stdio_command("D:\\OtherApp\\npx.cmd", ["x"]) == (
        "cmd", ["/c", "D:\\OtherApp\\npx.cmd", "x"])
    assert _resolve_stdio_command("run.bat", []) == ("cmd", ["/c", "run.bat"])
    # 普通 exe / 带扩展名可执行 → 原样(不该被包裹)
    assert _resolve_stdio_command("uvx", ["mcp-server-fetch"]) == ("uvx", ["mcp-server-fetch"])
    assert _resolve_stdio_command("python", ["-m", "srv"]) == ("python", ["-m", "srv"])
    # 非 Windows 不包裹
    monkeypatch.setattr(sys, "platform", "linux")
    assert _resolve_stdio_command("npx", ["-y", "srv"]) == ("npx", ["-y", "srv"])


def test_mcp_remote_tool_openai_schema():
    t = _MCPRemoteTool("s1", "search", "搜索", {"type": "object", "properties": {}}, None)
    schema = t.to_openai()
    assert schema["function"]["name"] == "search"
    assert schema["function"]["description"] == "搜索"


async def test_mcp_remote_tool_forwards_to_manager():
    """execute 转发给 manager.call(server, tool, args)"""
    class _FakeMgr:
        def __init__(self):
            self.last = None
        async def call(self, server, tool, args):
            self.last = (server, tool, args)
            return "mcp result"
    mgr = _FakeMgr()
    t = _MCPRemoteTool("s1", "search", "d", {}, mgr)
    out = await t.execute({"q": "x"}, None)
    assert out == "mcp result"
    assert mgr.last == ("s1", "search", {"q": "x"})


async def test_mcp_client_call_with_mock_conn():
    """MCPClient.call 转发到连接.call_tool,提取 content[].text;未连接返回占位"""
    class _FakeContent:
        def __init__(self, text):
            self.text = text
    class _FakeResult:
        def __init__(self, texts):
            self.content = [_FakeContent(t) for t in texts]
    class _FakeConn:
        async def call_tool(self, name, args):
            return _FakeResult(["hello", "world"])
    mgr = MCPClient()
    mgr._conns["s1"] = _FakeConn()
    assert await mgr.call("s1", "search", {"q": "x"}) == "hello\nworld"
    # 未连接的 server
    assert "未连接" in await mgr.call("ghost", "x", {})


async def test_server_conn_call_from_another_task():
    """跨 task 调用(2026-11-10 重构核心):start 的 task 与 call 的 task 不同也能通。

    复刻线上形态:owner task 在 ctx 内持 session;调用方(模拟 tool-loop task)经队列投递。
    旧版 AsyncExitStack 形态下这种跨 task 调用会触发 anyio cancel scope 报错。
    """
    entered_task_ids = []
    session_calls = []

    class _FakeStreams:
        async def __aenter__(self):
            entered_task_ids.append(id(asyncio.current_task()))
            return ("read", "write")

        async def __aexit__(self, *exc):
            return False

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def initialize(self):
            pass

        async def call_tool(self, name, args):
            session_calls.append((id(asyncio.current_task()), name, args))
            return f"ran:{name}"

    from mcp import ClientSession as _RealSession  # noqa: F401  确认可导入(环境健康检查)
    conn = _ServerConnection("fake", lambda: _FakeStreams())

    # 劫持 ClientSession(模块内懒导入,monkeypatch 源模块引用)
    import mcp
    real_session = mcp.ClientSession
    mcp.ClientSession = lambda r, w: _FakeSession()
    try:
        await conn.start()
        # 关键:在「另一个」task 里发起调用(与 start 不同 task)
        async def _caller():
            return await conn.call_tool("search", {"q": 1})
        out = await asyncio.create_task(_caller())
        assert out == "ran:search"
        await conn.stop()
    finally:
        mcp.ClientSession = real_session

    assert len(entered_task_ids) == 1                      # 上下文只 enter 过一次
    assert session_calls[0][0] == entered_task_ids[0]      # 调用跑在 owner task(非调用方 task)
    assert not conn._task or conn._task.done()             # 停机后 owner 退出


async def test_server_conn_error_isolation():
    """启动失败原样抛出(connect_all 隔离用);连断后的调用明确失败而非悬挂"""
    class _BoomCtx:
        async def __aenter__(self):
            raise RuntimeError("spawn failed")

        async def __aexit__(self, *exc):
            return False

    conn = _ServerConnection("boom", lambda: _BoomCtx())
    try:
        await conn.start()
        assert False, "should have raised"
    except RuntimeError as e:
        assert "spawn failed" in str(e)
    await conn.stop()   # 兜底清理(任务可能未建成)

    # 已 stop 的连接再调用 → 明确报错
    class _OkCtx(_BoomCtx):
        async def __aenter__(self):
            return ("r", "w")
    conn2 = _ServerConnection("ok", lambda: _OkCtx())
    with_closed = _ServerConnection("closed", lambda: _OkCtx())
    with_closed._closed = True
    try:
        await with_closed.call_tool("x", {})
        assert False, "should have raised"
    except RuntimeError:
        pass
