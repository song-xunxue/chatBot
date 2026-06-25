"""
客户端测试公共夹具：sys.path 注入（client/app + 项目根 shared）、临时 SQLite 路径、
Qt offscreen QApplication 会话夹具。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建客户端测试夹具

2026-06-25
变更说明：
  1. 新增 mock_ws 夹具：把 WSClient 线程化收发改为 no-op（保留信号能力），
     让 MainWindow 测试不再真起 WS 线程连 127.0.0.1:1，消除慢测/残留线程/flaky
"""
import os
import sys
from pathlib import Path

# Qt 离屏渲染（无显示器环境/CI 友好；必须在创建 QApplication 前设置）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# sys.path：client/app（模块同级导入）+ 项目根（shared）
_HERE = Path(__file__).resolve().parent            # client/tests
for _p in (str(_HERE.parent / "app"), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest


@pytest.fixture
def store(tmp_path):
    """临时 SQLite ChatStore（消息上限 5，便于测清理）"""
    from store.db import ChatStore
    s = ChatStore(tmp_path / "chat.db", message_limit=5)
    yield s
    s.close()


@pytest.fixture(scope="session")
def qapp():
    """会话级 QApplication（offscreen），供 UI 冒烟测试"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def mock_ws(monkeypatch):
    """把 WSClient 的线程化收发改为 no-op（**不** autouse，需显式选用）。

    问题：MainWindow 构造时会 ``self.ws.start()`` 真起一个 QThread 连
    ``ws://127.0.0.1:1``，连接必失败并进入指数退避重连循环，导致每个用例慢、
    且有残留线程/偶发 flaky。

    本夹具仅 patch 线程/网络副作用入口（``start``/``send_text``/``quit``/``wait``），
    保留 Qt 信号（``msg_received``/``connected``/``disconnected``/``error_occurred``）
    的声明能力——测试仍可直接调 ``win._on_msg(...)`` 驱动分发路径，信号也已正确接线。

    不 autouse：``test_ws_reconnect`` 需要真实的 WSClient 重连语义，不能被本夹具影响。
    """
    from net.ws_client import WSClient

    def _noop(self, *a, **k):
        return None

    # start：原方法真起线程；改为 no-op，构造 MainWindow 不再连网
    monkeypatch.setattr(WSClient, "start", _noop)
    # send_text：原方法向子线程事件循环投递队列任务；无线程时改为 no-op
    monkeypatch.setattr(WSClient, "send_text", _noop)
    # quit/wait：closeEvent 调用；改为 no-op 避免等待已不存在的线程
    monkeypatch.setattr(WSClient, "quit", _noop)
    monkeypatch.setattr(WSClient, "wait", _noop)

