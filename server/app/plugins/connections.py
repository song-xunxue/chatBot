"""
活跃 WS 连接注册表 ConnectionRegistry
维护 object_id -> set[WebSocket]，供主动推送（proactive_msg）与按对象广播。
单连接发送失败被隔离移除，不影响其他连接。单例。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 创建连接注册表：register/deregister/object_ids/broadcast
"""
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_registry: "ConnectionRegistry | None" = None


class ConnectionRegistry:
    """object_id -> 活跃 WebSocket 集合"""

    def __init__(self):
        self._conns: dict[str, set[WebSocket]] = {}

    def register(self, object_id: str, ws: WebSocket) -> None:
        """登记某对象的一个活跃连接（幂等）"""
        self._conns.setdefault(object_id, set()).add(ws)

    def deregister(self, ws: WebSocket) -> None:
        """移除某连接在所有对象下的登记（断开时调用）"""
        for conns in self._conns.values():
            conns.discard(ws)
        self._conns = {oid: c for oid, c in self._conns.items() if c}   # 清空集合

    def object_ids(self) -> list[str]:
        """当前有活跃连接的对象列表（供调度器逐对象触发 on_tick）"""
        return [oid for oid, c in self._conns.items() if c]

    async def broadcast(self, object_id: str, message: dict) -> int:
        """向某对象所有活跃连接发送消息；单连接失败隔离移除，返回成功发送数"""
        conns = self._conns.get(object_id, set())
        sent = 0
        for ws in list(conns):
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                logger.exception("broadcast to a connection failed, removed")
                conns.discard(ws)
        return sent


def get_connection_registry() -> ConnectionRegistry:
    """取全局连接注册表单例"""
    global _registry
    if _registry is None:
        _registry = ConnectionRegistry()
    return _registry
