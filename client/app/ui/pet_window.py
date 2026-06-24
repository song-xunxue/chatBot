"""
桌宠窗口 PetWindow（M6.1）
透明、无边框、始终置顶的桌面悬浮窗，显示白色小狐狸（默认 SVG）或上传的头像。
- 闲置：轻柔上下弹跳动画
- 拖拽：在桌面任意移动
- 左键单击：切换聊天主窗口显隐
- 右键：菜单（显示聊天 / 退出）
- shake()：收到 nudge 时左右抖动

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.1 创建桌宠：SVG 渲染 + 弹跳/拖拽/点击/抖动 + 右键菜单
"""
import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QMenu, QWidget

_FOX_SVG = os.path.join(os.path.dirname(__file__), "fox.svg")
_SIZE = 120


class PetWindow(QWidget):
    """桌宠：透明置顶悬浮窗"""

    def __init__(self, on_toggle_chat, on_quit, rest=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(_SIZE, _SIZE)
        self.setWindowTitle("小狐狸")
        self._on_toggle = on_toggle_chat
        self._on_quit = on_quit
        self._rest = rest
        self._drag_offset = None
        self._pressed_at = None
        self._moved = False
        self._anim = None

        self.label = QLabel(self)
        self.label.setFixedSize(_SIZE, _SIZE)
        self._base_y = 0
        self._load_appearance()
        self._start_idle()

    # —— 外观 ——
    def _load_appearance(self):
        """优先用上传的头像字节，否则用内置 fox.svg"""
        pm = None
        if self._rest is not None:
            data = self._rest.get_pet_avatar_bytes()
            if data:
                pm = QPixmap()
                pm.loadFromData(data)
                if pm.isNull():
                    pm = None
        if pm is None:
            pm = self._render_fox_svg()
        self.label.setPixmap(pm.scaled(_SIZE, _SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _render_fox_svg(self) -> QPixmap:
        """把内置 fox.svg 渲染为透明背景 QPixmap"""
        with open(_FOX_SVG, "rb") as f:
            renderer = QSvgRenderer(QByteArray(f.read()))
        pm = QPixmap(_SIZE, _SIZE)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
        return pm

    def reload_appearance(self):
        """重新拉取头像（上传/修改后调用）"""
        self._load_appearance()

    # —— 闲置弹跳动画 ——
    def _start_idle(self):
        self._idle = QPropertyAnimation(self.label, b"geometry", self)
        self._idle.setDuration(1400)
        self._idle.setLoopCount(-1)                          # 无限循环
        self._idle.setEasingCurve(QEasingCurve.InOutSine)
        g = self.label.geometry()
        self._idle.setKeyValueAt(0.0, g)
        self._idle.setKeyValueAt(0.5, g.adjusted(0, -6, 0, -6))   # 上浮 6px
        self._idle.setKeyValueAt(1.0, g)
        self._idle.start()

    # —— nudge 抖动 ——
    def shake(self):
        """左右快速抖动（收到 nudge 时调用）"""
        anim = QPropertyAnimation(self.label, b"geometry", self)
        anim.setDuration(420)
        anim.setLoopCount(1)
        g = self.label.geometry()
        anim.setKeyValueAt(0.0, g)
        for i, dx in enumerate([5, -5, 4, -4, 3, -3, 0]):
            anim.setKeyValueAt((i + 1) / 7, g.adjusted(dx, 0, dx, 0))
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._shake_anim = anim   # 持引用防 GC

    # —— 鼠标交互 ——
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._pressed_at = e.position().toPoint()
            self._moved = False

    def mouseMoveEvent(self, e):
        if (e.buttons() & Qt.LeftButton) and self._drag_offset is not None:
            if (e.position().toPoint() - self._pressed_at).manhattanLength() > 4:
                self._moved = True
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            if not self._moved and self._on_toggle is not None:
                self._on_toggle()                            # 左键单击 → 切换聊天窗
            self._drag_offset = None

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        act_chat = menu.addAction("显示/隐藏聊天")
        act_quit = menu.addAction("退出")
        action = menu.exec(e.globalPos())
        if action == act_chat and self._on_toggle is not None:
            self._on_toggle()
        elif action == act_quit and self._on_quit is not None:
            self._on_quit()
