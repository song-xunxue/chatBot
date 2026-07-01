"""
QQ REST 消息发送(httpx)
封装发私聊(C2C)消息:走「被动回复」(带 msg_id),60 分钟窗口内有效、不耗主动消息月配额。

接口(查 QQ 文档「发送消息」确认):
  POST {api_base}/v2/users/{openid}/messages
  header: Authorization: QQBot {access_token}
  body:   {"content":..., "msg_type":0(文本), "msg_id":...(被动回复必带), "msg_seq":...(防同 msg_id 重复)}

M1 echo 链路:webhook 收 C2C_MESSAGE_CREATE → send_c2c_message(openid, "收到:xxx", msg_id=...)。
M2 起真实回复由 pipeline 产出;主动消息(无 msg_id,耗月配额)留 M8 代人聊天。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建 api_client:send_c2c_message(被动回复,带 msg_id/msg_seq)+ httpx 单例
"""
import logging

import httpx

from core.config import settings
from qq.auth import get_access_token

logger = logging.getLogger(__name__)

# httpx 异步单例(与 auth._client 分离:不同 base_url;复用连接池;测试 monkeypatch 注入 MockTransport)
_client: httpx.AsyncClient | None = None


async def init_client() -> None:
    """lifespan 启动时创建 httpx 异步客户端单例(base_url 指向 QQ 消息 API)"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)


async def close_client() -> None:
    """lifespan 关闭时释放 httpx 客户端"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def send_c2c_message(openid: str, content: str, *, msg_id: str = "", msg_seq: int = 1) -> dict:
    """发私聊消息(被动回复优先:带 msg_id 不耗主动月配额,60 分钟窗口内有效)

    参数:
        openid:  QQ 用户 openid(事件 d.author.user_openid)
        content: 文本内容
        msg_id:  用户消息 id(被动回复必填;留空则成主动消息,耗月配额,M8 代人聊天用)
        msg_seq: 回复序号,与 msg_id 联用防同 msg_id 重复发送(QQ 规则:相同 msg_id+msg_seq 重复会失败)
    返回:
        QQ 响应 {"id": 消息id, "timestamp": 发送时间}
    """
    assert _client is not None, "httpx client 未初始化,请在 lifespan 调 init_client"
    token = await get_access_token()
    headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}
    payload: dict = {"content": content, "msg_type": 0, "msg_seq": msg_seq}
    if msg_id:
        payload["msg_id"] = msg_id  # 被动回复(回复类),窗口 60min
    resp = await _client.post(f"{settings.qq_api_base}/v2/users/{openid}/messages",
                              headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()


async def send_download(url: str) -> bytes:
    """下载 QQ 附件(图片等)原始 bytes。QQ 附件 CDN URL 需鉴权(QQBot access_token)。
    M-vision:M2.6 图片消息解析时调,失败抛异常由调用方(webhook._describe_image)软失败兜底。"""
    assert _client is not None, "httpx client 未初始化,请在 lifespan 调 init_client"
    token = await get_access_token()
    headers = {"Authorization": f"QQBot {token}"}
    resp = await _client.get(url, headers=headers, follow_redirects=True)
    resp.raise_for_status()
    return resp.content
