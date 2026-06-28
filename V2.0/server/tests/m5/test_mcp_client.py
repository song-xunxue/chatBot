"""
MCP client 单测:parse_mcp_servers(JSON 解析/降级)+ _MCPRemoteTool(转发/ schema)+
MCPClient.call(mock session 转发)。不真连外部 server(连接集成留真实验证)。

作者: 李文煜
日期: 2026-06-28
"""
from mcp_client import parse_mcp_servers, MCPClient, _MCPRemoteTool


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


async def test_mcp_client_call_with_mock_session():
    """MCPClient.call 转发到 session.call_tool,提取 content[].text"""
    class _FakeContent:
        def __init__(self, text):
            self.text = text
    class _FakeResult:
        def __init__(self, texts):
            self.content = [_FakeContent(t) for t in texts]
    class _FakeSession:
        async def call_tool(self, name, args):
            return _FakeResult(["hello", "world"])
    mgr = MCPClient()
    mgr._sessions["s1"] = _FakeSession()
    assert await mgr.call("s1", "search", {"q": "x"}) == "hello\nworld"
    # 未连接的 server
    assert "未连接" in await mgr.call("ghost", "x", {})
