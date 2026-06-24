"""
面板代答请求订阅广播器（V1.1 M13）
维护面板 WS 连接集合，广播 takeover_request/resolved 到所有订阅面板。
与 ConnectionRegistry 解耦（后者按 object_id 路由客户端，panel_bus 路由面板订阅者）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. V1.1 M13 创建 panel_bus：subscribe/unsubscribe/broadcast_to_panels（失败隔离）
"""
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_bus: set[WebSocket] = set()


def subscribe(ws: WebSocket) -> None:
    _bus.add(ws)


def unsubscribe(ws: WebSocket) -> None:
    _bus.discard(ws)


async def broadcast_to_panels(message: dict) -> int:
    """向所有订阅面板发送消息；单连接失败隔离移除，返回成功发送数"""
    sent = 0
    for ws in list(_bus):
        try:
            await ws.send_json(message)
            sent += 1
        except Exception:
            logger.exception("panel broadcast failed, removed")
            _bus.discard(ws)
    return sent


def panel_count() -> int:
    return len(_bus)
