"""
聊天视图：消息气泡列表（流式渲染 + 富内容）+ 输入栏。
- BubbleRow：单条消息行（头像 + 文本气泡 + 富内容图像/语音），AI 左 / 用户右
- ChatView：QScrollArea 内垂直排列气泡 + 底部输入栏；流式 API（start/append/finalize）
温暖拟人化样式由 theme.QSS 驱动（objectName）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建聊天视图：气泡 + 流式光标 + 输入栏
  2. M5 多模态：BubbleRow 支持 rich（图像缩略图/语音条）渲染
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

_AVATAR = {"assistant": "🐱", "user": "🧑"}
_CURSOR = "▌"


class BubbleRow(QWidget):
    """单条消息行：头像 + 内容列(文本气泡 + 富内容)；assistant 左对齐，user 右对齐"""

    def __init__(self, role: str, text: str = "", ts: int = 0, parent=None):
        super().__init__(parent)
        self.role = role
        self.bubble = QLabel(text)
        self.bubble.setWordWrap(True)
        self.bubble.setMaximumWidth(260)
        self.bubble.setObjectName("bubbleAI" if role == "assistant" else "bubbleUser")
        self.bubble.setTextFormat(Qt.PlainText)
        # 内容列：文本气泡 + 富内容垂直堆叠
        self.content = QWidget()
        self._content_layout = QVBoxLayout(self.content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        self._content_layout.addWidget(self.bubble)
        avatar = QLabel(_AVATAR.get(role, "·"))

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 2, 8, 2)
        if role == "assistant":
            row.addWidget(avatar); row.addWidget(self.content); row.addStretch()
        else:
            row.addStretch(); row.addWidget(self.content); row.addWidget(avatar)

    def set_text(self, text: str, streaming: bool = False) -> None:
        self.bubble.setText(text + (_CURSOR if streaming and text else ""))

    def append(self, delta: str) -> None:
        self.bubble.setText(self.bubble.text().rstrip(_CURSOR) + delta + _CURSOR)

    def finalize(self, text: str, held: bool = False) -> None:
        self.bubble.setText(text if not held else "对方正在组织语言…")

    def add_rich(self, rich: dict) -> None:
        """渲染富内容：image/sticker 用 RichImageWidget，audio 用 RichAudioWidget"""
        if not rich:
            return
        from ui.rich_widgets import RichAudioWidget, RichImageWidget
        for spec in (rich.get("image") or []):
            self._content_layout.addWidget(RichImageWidget(spec))
        for spec in (rich.get("sticker") or []):
            self._content_layout.addWidget(RichImageWidget(spec))
        for spec in (rich.get("audio") or []):
            self._content_layout.addWidget(RichAudioWidget(spec))


class ChatView(QWidget):
    """聊天主区：气泡列表 + 输入栏"""

    send_text = Signal(str)   # 用户发送文字

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 消息滚动区
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._list = QVBoxLayout(self._container)
        self._list.setContentsMargins(6, 8, 6, 8)
        self._list.setSpacing(4)
        self._list.addStretch()                      # 顶部弹簧，消息从上往下排
        self.scroll.setWidget(self._container)
        root.addWidget(self.scroll, 1)

        # 输入栏
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 8, 10, 8)
        bar.setSpacing(8)
        self.attach = QPushButton("📎", self)
        self.attach.setObjectName("iconBtn")
        self.attach.setToolTip("附件（M5 后续）")
        self.attach.setEnabled(False)
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("输入消息，回车发送…")
        self.input.returnPressed.connect(self._emit_send)
        self.send = QPushButton("发送", self)
        self.send.setObjectName("sendBtn")
        self.send.clicked.connect(self._emit_send)
        bar.addWidget(self.attach); bar.addWidget(self.input, 1); bar.addWidget(self.send)
        root.addLayout(bar)

    def _emit_send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.send_text.emit(text)

    # —— 消息操作 ——
    def add_message(self, role: str, text: str, ts: int = 0, rich: dict | None = None):
        row = BubbleRow(role, text, ts)
        if rich:
            row.add_rich(rich)
        self._list.insertWidget(self._list.count() - 1, row)   # 插在 stretch 之前
        self._scroll_bottom()
        return row

    def add_system(self, text: str):
        lbl = QLabel(text)
        lbl.setObjectName("bubbleSys")
        lbl.setAlignment(Qt.AlignCenter)
        self._list.insertWidget(self._list.count() - 1, lbl)
        self._scroll_bottom()

    def start_ai_bubble(self, ts: int = 0) -> BubbleRow:
        row = BubbleRow("assistant", "", ts)
        self._list.insertWidget(self._list.count() - 1, row)
        self._scroll_bottom()
        return row

    def append_chunk(self, row: BubbleRow, delta: str):
        if row is not None and delta:
            row.append(delta)
            self._scroll_bottom()

    def finalize_ai(self, row: BubbleRow, text: str, held: bool = False, rich: dict | None = None):
        if row is not None:
            row.finalize(text, held=held)
            if rich:
                row.add_rich(rich)
            self._scroll_bottom()

    def _scroll_bottom(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
