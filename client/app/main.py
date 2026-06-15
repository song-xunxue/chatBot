"""
MyChat 客户端入口（M1.5 tracer bullet）
主聊天窗口 + 输入发送 + WebSocket 连接 + 消息回显

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.3 创建最小应用：主窗口占位 + 系统托盘
  2. M1.5 接入 WebSocket：输入框/发送/消息显示，打通端到端 tracer bullet
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from net.ws_client import WSClient  # 同级导入：WebSocket 客户端


# 服务端地址（从环境变量读，默认本地；部署后指向服务器 IPv4）
SERVER_WS_URL = os.environ.get("CLIENT_WS_URL", "ws://127.0.0.1:8000/ws")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "change-me-please")


class ChatWindow(QMainWindow):
    """主聊天窗口：消息显示 + 输入发送（M1 占位 UI，后续接入消息气泡/多模态/桌宠）"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyChat")
        self.resize(380, 600)

        # 1.布局：消息区 + 输入栏
        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.view = QTextEdit(central)  # 消息显示区（只读）
        self.view.setReadOnly(True)
        layout.addWidget(self.view)

        bar = QHBoxLayout()
        self.input = QLineEdit(central)  # 输入框
        self.input.setPlaceholderText("输入消息，回车发送...")
        self.input.returnPressed.connect(self._on_send)
        self.btn = QPushButton("发送", central)  # 发送按钮
        self.btn.clicked.connect(self._on_send)
        bar.addWidget(self.input)
        bar.addWidget(self.btn)
        layout.addLayout(bar)

        self.setCentralWidget(central)

        # 2.WebSocket 客户端线程（启动后自动连接服务端）
        self.ws = WSClient(SERVER_WS_URL, ACCESS_TOKEN)
        self.ws.msg_received.connect(self._on_msg)
        self.ws.connected.connect(lambda: self._append("【系统】已连接服务端"))
        self.ws.error_occurred.connect(lambda e: self._append(f"【错误】{e}"))
        self.ws.start()

    def _on_send(self):
        """发送按钮/回车：把输入文本发给服务端"""
        text = self.input.text().strip()
        if not text:
            return
        self._append(f"【我】{text}")
        self.ws.send_text(text)
        self.input.clear()

    def _on_msg(self, data: dict):
        """收到服务端消息：按类型显示"""
        t = data.get("type")
        payload = data.get("payload", {})
        if t == "ai_done":
            self._append(f"【AI】{payload.get('text', '')}")
        elif t == "error":
            self._append(f"【错误】{payload.get('message', '')}")
        else:
            self._append(f"【{t}】{payload}")

    def _append(self, line: str):
        """追加一行到消息区"""
        self.view.append(line)

    def closeEvent(self, event):
        """关闭时终止 WS 线程"""
        self.ws.quit()
        self.ws.wait(2000)
        super().closeEvent(event)


def main():
    """客户端入口"""
    app = QApplication(sys.argv)

    window = ChatWindow()
    window.show()

    # 系统托盘（用 Qt 内置图标，避免依赖外部资源；桌宠形态在 M6 实现）
    tray = QSystemTrayIcon(app)
    tray.setIcon(app.style().standardIcon(QStyle.SP_ComputerIcon))
    tray.setToolTip("MyChat")
    menu = QMenu()
    act_quit = QAction("退出")
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
