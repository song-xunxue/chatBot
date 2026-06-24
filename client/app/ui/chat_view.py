"""
聊天视图：消息气泡列表（流式渲染 + 富内容）+ 输入栏。
- BubbleRow：单条消息行（头像 + 气泡 + 富内容），AI 左 / 用户右（微信式）
- ChatView：QScrollArea 内垂直排列气泡 + 底部输入栏；流式 API（start/append/finalize）
微信风格由 theme.QSS 驱动（objectName）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建聊天视图：气泡 + 流式光标 + 输入栏
  2. M5 多模态：BubbleRow 支持 rich（图像缩略图/语音条）渲染

2026-06-25
变更说明：
  1. 重构为微信气泡：QFrame 气泡(#95EC69/#FFF)+圆形头像；头像由 MainWindow 注入
  2. 输入栏按钮改用 SVG 图标（smile/clip/mic），去掉 emoji 文字
"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

_HERE = Path(__file__).resolve().parent                  # client/app/ui
_SMILE_SVG = str(_HERE / "smile.svg")
_CLIP_SVG = str(_HERE / "clip.svg")
_MIC_SVG = str(_HERE / "mic.svg")
_AVATAR_PX = 40
_DEFAULT_AVATAR_SVG = str(_HERE / "avatar_default.svg")


def _pixmap_from_svg(svg_path: str, size: int = 22) -> QPixmap:
    """SVG → 指定尺寸 QPixmap（QSvgRenderer 渲染，比 QPixmap(svg) 在各平台可靠）"""
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtGui import QImage, QPainter
    renderer = QSvgRenderer(svg_path)
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    renderer.render(p)
    p.end()
    return QPixmap.fromImage(img)
_BUBBLE_MAX_W = 360
_CURSOR = "▌"


class BubbleRow(QWidget):
    """单条消息行：头像 + 气泡(QFrame) + 富内容；assistant 左对齐，user 右对齐。

    avatar_pixmap 为 None 时显示空头像占位（MainWindow 默认注入默认 svg）。"""

    def __init__(self, role: str, text: str = "", ts: int = 0, avatar_pixmap: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.role = role

        # 气泡容器 QFrame（微信式小圆角，objectName 驱动 QSS 配色）
        self.bubble_frame = QFrame()
        self.bubble_frame.setObjectName("bubbleUser" if role == "user" else "bubbleAI")
        bl = QHBoxLayout(self.bubble_frame)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(0)
        # 文本 QLabel：历史代码/测试访问 row.bubble.text()，保留 bubble 指向内容 QLabel
        self.bubble = QLabel(text)
        self.bubble.setObjectName("bubbleContentUser" if role == "user" else "bubbleContentAI")
        self.bubble.setWordWrap(True)
        self.bubble.setMaximumWidth(_BUBBLE_MAX_W)
        self.bubble.setTextFormat(Qt.PlainText)
        self.content_label = self.bubble             # 别名（新代码语义名）
        bl.addWidget(self.bubble)

        # 头像（圆形遮罩由 MainWindow 注入的 pixmap 已是圆形；这里只固定尺寸）
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(_AVATAR_PX, _AVATAR_PX)
        self._set_avatar(avatar_pixmap)

        # 富内容列：气泡下方再堆叠图像/语音（沿用历史行为）
        self._rich_holder = None  # 按需创建

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)
        if role == "assistant":
            row.addWidget(self.avatar_label, 0, Qt.AlignTop)
            row.addWidget(self.bubble_frame, 0, Qt.AlignTop)
            row.addStretch()
        else:
            row.addStretch()
            row.addWidget(self.bubble_frame, 0, Qt.AlignTop)
            row.addWidget(self.avatar_label, 0, Qt.AlignTop)

    # —— 头像 ——
    def _set_avatar(self, pm: QPixmap | None):
        if pm is not None and not pm.isNull():
            self.avatar_label.setPixmap(pm.scaled(
                _AVATAR_PX, _AVATAR_PX, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        else:
            # None 兜底默认头像（避免空白方块，与左列表降级一致）
            self.avatar_label.setPixmap(_pixmap_from_svg(_DEFAULT_AVATAR_SVG, _AVATAR_PX))

    def set_avatar(self, pm: QPixmap | None):
        """外部更新头像（切换对象后补气泡头像）"""
        self._set_avatar(pm)

    # —— 文本 ——
    def set_text(self, text: str, streaming: bool = False) -> None:
        self.content_label.setText(text + (_CURSOR if streaming and text else ""))

    def append(self, delta: str) -> None:
        self.content_label.setText(self.content_label.text().rstrip(_CURSOR) + delta + _CURSOR)

    def finalize(self, text: str, held: bool = False) -> None:
        self.content_label.setText(text if not held else "对方正在组织语言…")

    # —— 富内容 ——
    def _ensure_rich_holder(self):
        if self._rich_holder is None:
            self._rich_holder = QWidget()
            self._rich_layout = QVBoxLayout(self._rich_holder)
            self._rich_layout.setContentsMargins(0, 0, 0, 0)
            self._rich_layout.setSpacing(4)
            # 富内容列紧贴气泡下方（与头像同侧）：assistant 在头像后第 2 位，user 在 stretch 后
            lay = self.layout()
            idx = 2 if self.role == "assistant" else lay.count() - 2
            lay.insertWidget(idx, self._rich_holder, 0, Qt.AlignTop)

    def add_rich(self, rich: dict) -> None:
        """渲染富内容：image/sticker 用 RichImageWidget，audio 用 RichAudioWidget"""
        if not rich:
            return
        from ui.rich_widgets import RichAudioWidget, RichImageWidget
        self._ensure_rich_holder()
        for spec in (rich.get("image") or []):
            self._rich_layout.addWidget(RichImageWidget(spec))
        for spec in (rich.get("sticker") or []):
            self._rich_layout.addWidget(RichImageWidget(spec))
        for spec in (rich.get("audio") or []):
            self._rich_layout.addWidget(RichAudioWidget(spec))

    def add_local_image(self, path: str, max_w: int = 150) -> None:
        """添加本地图片（表情包等）到内容列"""
        pm = QPixmap(path)
        if pm.isNull():
            return
        lbl = QLabel()
        lbl.setPixmap(pm.scaledToWidth(max_w, Qt.SmoothTransformation))
        self._ensure_rich_holder()
        self._rich_layout.addWidget(lbl)


def _icon_button(obj_name: str, svg_path: str, tooltip: str) -> QPushButton:
    """构造一个 SVG 图标按钮（细线风格，统一 iconBtn 样式）"""
    btn = QPushButton()
    btn.setObjectName(obj_name)
    btn.setToolTip(tooltip)
    pm = _pixmap_from_svg(svg_path, 22)
    if not pm.isNull():
        btn.setIcon(pm)
        btn.setIconSize(pm.size())   # 22×22
    btn.setFixedSize(34, 34)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


class ChatView(QWidget):
    """聊天主区：气泡列表 + 输入栏"""

    send_text = Signal(str)   # 用户发送文字
    attach_image = Signal()   # 点击附件（选图，视觉理解）
    attach_audio = Signal()   # 点击麦克风（选音频，语音识别）
    sticker_clicked = Signal()   # 点击笑脸（打开表情包）

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
        self._list.setSpacing(6)
        self._list.addStretch()                      # 顶部弹簧，消息从上往下排
        self.scroll.setWidget(self._container)
        root.addWidget(self.scroll, 1)

        # 输入栏
        bar_frame = QFrame()
        bar_frame.setObjectName("inputBar")
        bar = QHBoxLayout(bar_frame)
        bar.setContentsMargins(10, 6, 10, 6)
        bar.setSpacing(6)
        self.sticker = _icon_button("iconBtn", _SMILE_SVG, "表情包")
        self.sticker.clicked.connect(lambda: self.sticker_clicked.emit())
        self.attach = _icon_button("iconBtn", _CLIP_SVG, "发送图片（视觉理解）")
        self.attach.clicked.connect(lambda: self.attach_image.emit())
        self.mic = _icon_button("iconBtn", _MIC_SVG, "发送语音（语音识别）")
        self.mic.clicked.connect(lambda: self.attach_audio.emit())
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("输入消息，回车发送…")
        self.input.returnPressed.connect(self._emit_send)
        self.send = QPushButton("发送", self)
        self.send.setObjectName("sendBtn")
        self.send.setCursor(Qt.PointingHandCursor)
        self.send.clicked.connect(self._emit_send)
        bar.addWidget(self.sticker); bar.addWidget(self.attach); bar.addWidget(self.mic)
        bar.addWidget(self.input, 1); bar.addWidget(self.send)
        root.addWidget(bar_frame)

    def _emit_send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.send_text.emit(text)

    # —— 消息操作 ——
    def clear(self):
        """清空所有消息气泡（切换聊天对象时调用，避免历史叠加重复显示）"""
        for i in range(self._list.count() - 1, -1, -1):   # 倒序删，避免索引错乱
            item = self._list.takeAt(i)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()
        self._list.addStretch()   # 重新加顶部弹簧（消息从上往下排）

    def add_message(self, role: str, text: str, ts: int = 0, rich: dict | None = None,
                    avatar_pixmap: QPixmap | None = None):
        row = BubbleRow(role, text, ts, avatar_pixmap=avatar_pixmap)
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

    def start_ai_bubble(self, ts: int = 0, avatar_pixmap: QPixmap | None = None) -> BubbleRow:
        row = BubbleRow("assistant", "", ts, avatar_pixmap=avatar_pixmap)
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

    def add_sticker(self, path: str, avatar_pixmap: QPixmap | None = None):
        """以用户气泡形式发送一张本地表情包图片"""
        row = BubbleRow("user", "", ts=0, avatar_pixmap=avatar_pixmap)
        row.add_local_image(path)
        self._list.insertWidget(self._list.count() - 1, row)
        self._scroll_bottom()

    def set_background(self, path: str):
        """设置聊天区背景图（QSS background-image；气泡自带底色保持可读）"""
        norm = path.replace("\\", "/")
        self.scroll.setStyleSheet(
            f"background-image: url('{norm}'); background-repeat: no-repeat; background-position: center;"
        )
