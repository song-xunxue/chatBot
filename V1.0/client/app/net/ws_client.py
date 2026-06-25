"""
WebSocket 客户端（实时主通道）
在 QThread 中运行 asyncio 事件循环，与 Qt 主线程通过信号通信。
M5：增加指数退避自动重连（1s→2s→…→30s 封顶），断线自动恢复，重连后发 connected 信号。

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.5 创建 WS 客户端：长连接 + 收发消息，信号驱动 UI 更新

2026-06-24
变更说明：
  1. M5 增加自动重连（指数退避 1s..30s）+ disconnected 信号；send_text 容错（未连入队失败不崩）
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

import websockets  # 第三方：WebSocket 客户端实现
from PySide6.QtCore import QThread, Signal  # Qt 线程与信号槽

logger = logging.getLogger(__name__)

# 引入跨端共享协议（shared 在项目根，加入 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.protocol import envelope, TYPE_USER_MSG, now_ts  # noqa: E402

# 重连退避参数
_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX = 30.0
_BACKOFF_FACTOR = 2.0


class WSClient(QThread):
    """WebSocket 客户端线程：维护长连接，收发消息；断线指数退避自动重连"""

    # 信号：收到消息 / 已连接(每次成功连接触发) / 断开 / 出错
    msg_received = Signal(dict)
    connected = Signal()
    disconnected = Signal()
    error_occurred = Signal(str)

    def __init__(self, ws_url: str, token: str, object_id: str = "default",
                 auto_reconnect: bool = True):
        super().__init__()
        self._url = f"{ws_url}?token={token}"  # token 经 query 参数鉴权（见 03-接口 §2）
        self._object_id = object_id
        self._auto_reconnect = auto_reconnect
        self._ws = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._send_queue: asyncio.Queue = asyncio.Queue()  # 主线程投递、子线程消费
        self._stop = asyncio.Event()                        # 停止信号（quit 时置位）

    def run(self):
        """线程入口：运行 asyncio 事件循环"""
        asyncio.run(self._main())

    async def _main(self):
        """主协程：连接 + 并行收发；断开后指数退避重连"""
        self._loop = asyncio.get_event_loop()
        backoff = _BACKOFF_INITIAL
        while not self._stop.is_set():
            try:
                async with websockets.connect(self._url) as ws:
                    self._ws = ws
                    self.connected.emit()
                    backoff = _BACKOFF_INITIAL            # 连上即重置退避
                    # 并行：接收 + 发送，任一结束（断线）则退出 with 重新连
                    await asyncio.gather(self._receiver(ws), self._sender(ws))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.error_occurred.emit(f"WS 连接错误: {e}")
            # 走到这里说明连接断开
            self._ws = None
            self.disconnected.emit()
            if not self._auto_reconnect or self._stop.is_set():
                break
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)  # 退避期间可被 quit 唤醒
                break                                                        # stop 置位 → 退出
            except asyncio.TimeoutError:
                backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_MAX)       # 指数退避，封顶 30s

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
        while not self._stop.is_set():
            payload = await self._send_queue.get()
            if payload is None:
                break
            await ws.send(json.dumps(payload))

    def send_text(self, text: str):
        """主线程调用：发送一条文字（线程安全投递到 asyncio 队列）。
        未连接时投递仍成功（入队），连接恢复后由 _sender 发出。"""
        if self._loop is None:
            return
        msg = envelope(TYPE_USER_MSG, {"text": text}, object_id=self._object_id, ts=now_ts())
        # run_coroutine_threadsafe：从主线程向子线程事件循环投递任务
        asyncio.run_coroutine_threadsafe(self._send_queue.put(msg), self._loop)

    def quit(self):
        """停止线程：置位 stop 事件并投递哨兵唤醒 _sender。
        注意 Event.set() 是普通方法（非协程），用 call_soon_threadsafe 调度；
        Queue.put() 是协程，用 run_coroutine_threadsafe。"""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
            asyncio.run_coroutine_threadsafe(self._send_queue.put(None), self._loop)
        super().quit()

