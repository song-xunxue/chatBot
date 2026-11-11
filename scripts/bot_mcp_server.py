"""
Bot 能力 MCP server(反向暴露,2026-11-08 第二批):
把bot面板的能力以 MCP 工具暴露给本机任意 MCP 客户端(如 Claude Code 的 .mcp.json)。
薄壳设计:全部工具经 HTTP 转发本机面板 REST(localhost:8091),不直连 redis/WS——
server 进程才持有 NapCat 反向 WS 出站通道,本进程只做 REST 转发。

工具清单:
  get_status()                       bot健康状态(服务/OneBot 连接)
  get_chat_history(oid, limit)       最近会话消息(默认 20 条)
  get_mood(oid)                      当前心情值
  send_message(oid, content)         以bot人设身份发 QQ 消息(写操作!)

接入(Claude Code .mcp.json / claude mcp add):
  {"chatbot": {"command": "C:/Users/26904/anaconda3/envs/mychat/python.exe",
               "args": ["D:/code/Git_Local/ChatBot/scripts/bot_mcp_server.py"]}}

日期: 2026-11-08
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

PANEL = os.environ.get("PANEL_BASE", "http://127.0.0.1:8091")
TOKEN = os.environ.get("PANEL_TOKEN", "114507xX")   # 本机使用;换 token 同步环境变量

mcp = FastMCP("chatbot-qingxun")


def _headers() -> dict:
    return {"X-Access-Token": TOKEN}


@mcp.tool()
def get_status() -> str:
    """bot bot 健康状态(服务在线/OneBot 连接/QQ 号)"""
    r = httpx.get(f"{PANEL}/health", timeout=8)
    return r.text


@mcp.tool()
def get_chat_history(oid: str, limit: int = 20) -> str:
    """取bot与某个 QQ 号的最近会话消息(默认 20 条,oid=对方 QQ 号)"""
    r = httpx.get(f"{PANEL}/api/v1/chat/{oid}/messages", headers=_headers(),
                  params={"limit": limit}, timeout=10)
    if r.status_code != 200:
        return f"查询失败 HTTP {r.status_code}: {r.text[:300]}"
    data = r.json()
    if isinstance(data, list):
        items = data
    else:
        items = data.get("messages") or data.get("items") or []
    out = []
    for m in items[-limit:]:
        who = m.get("sender") or m.get("role") or "?"
        out.append(f"[{who}] {str(m.get('content', ''))[:200]}")
    return "\n".join(out) if out else "(无消息)"


@mcp.tool()
def get_mood(oid: str) -> str:
    """取bot对某个 QQ 号的当前心情值(0-1)与档位"""
    r = httpx.get(f"{PANEL}/api/v1/mood/{oid}", headers=_headers(), timeout=10)
    return r.text[:500]


@mcp.tool()
def send_message(oid: str, content: str) -> str:
    """以bot的人设身份给某个 QQ 号发一条消息(写操作;content 为要发的文本)"""
    r = httpx.post(f"{PANEL}/api/v1/takeover/{oid}/send", headers=_headers(),
                   json={"content": content}, timeout=60)
    if r.status_code != 200:
        return f"发送失败 HTTP {r.status_code}: {r.text[:300]}"
    d = r.json()
    return f"已发送(delivered={d.get('delivered')}, mode={d.get('mode')})"


if __name__ == "__main__":
    mcp.run()   # stdio(默认)
