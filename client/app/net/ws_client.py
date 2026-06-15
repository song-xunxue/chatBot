"""
WebSocket 客户端（实时主通道）
在 QThread 中运行 asyncio 事件循环，与 Qt 主线程通过信号通信

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.5 创建 WS 客户端：长连接 + 收发消息，信号驱动 UI 更新
"""
import asyncio
import json
import sys
from pathlib import Path

import websockets  # 第三方：WebSocket 客户端实现
from PySide6.QtCore import QThread, Signal  # Qt 线程与信号槽

# 引入跨端共享协议（shared 在项目根，加入 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.protocol import envelope, TYPE_USER_MSG, now_ts  # noqa: E402


class WSClient(QThread):
    """WebSocket 客户端线程：维护长连接，收发消息"""

    # 信号：收到消息 / 已连接 / 出错（信号在子线程发射，Qt 自动跨线程传递到主线程槽）
    msg_received = Signal(dict)
    connected = Signal()
    error_occurred = Signal(str)

    def __init__(self, ws_url: str, token: str, object_id: str = "default"):
        super().__init__()
        self._url = f"{ws_url}?token={token}"  # token 经 query 参数鉴权（见 03-接口 §2）
        self._object_id = object_id
        self._ws = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._send_queue: asyncio.Queue = asyncio.Queue()  # 主线程投递、子线程消费

    def run(self):
        """线程入口：运行 asyncio 事件循环"""
        asyncio.run(self._main())

    async def _main(self):
        """主协程：连接 + 并行收发"""
        self._loop = asyncio.get_event_loop()
        try:
            async with websockets.connect(self._url) as ws:
                self._ws = ws
                self.connected.emit()
                # 并行运行接收循环与发送循环
                await asyncio.gather(self._receiver(ws), self._sender(ws))
        except Exception as e:
            self.error_occurred.emit(f"WS 连接错误: {e}")

    async def _receiver(self, ws):
        """接收循环：把每条消息通过信号发给主线程"""
        async for raw in ws:
            try:
                data = json.loads(raw)
                self.msg_received.emit(data)
            except Exception as e:
                self.error_occurred.emit(f"解析消息失败: {e}")

    async def _sender(self, ws):
        """发送循环：从队列取消息发出"""
        while True:
            payload = await self._send_queue.get()
            await ws.send(json.dumps(payload))

    def send_text(self, text: str):
        """主线程调用：发送一条文字（线程安全投递到 asyncio 队列）"""
        if self._loop is None:
            return
        msg = envelope(TYPE_USER_MSG, {"text": text}, object_id=self._object_id, ts=now_ts())
        # run_coroutine_threadsafe：从主线程向子线程事件循环投递任务
        asyncio.run_coroutine_threadsafe(self._send_queue.put(msg), self._loop)
