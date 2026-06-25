"""
富内容展示组件：图像缩略图(异步加载+点击放大)、语音播放条、心情 emoji 映射。
- 真实 http(s) URL：图像异步加载、语音用 QMediaPlayer 播放
- stub:// 或加载失败：显示占位（当前 provider 为 stub，真实能力待 Q-10）

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建富内容组件：RichImageWidget / RichAudioWidget / mood_emoji
"""
import httpx
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

# 心情标签 → emoji（与服务端 mood_dynamic._label 对应）
MOOD_EMOJI = {
  "开心": "◍˃ᵕ˂◍",
  "愉悦": "˗ˋˏ♡ˎˊ˗",
  "平静": "◌",
  "低落": "˚‧º·(˚ ˃̣̣̥᷄⌓˂̣̣̥᷅ )‧º·˚",
  "难过": "╥﹏╥"
                }


def mood_emoji(label: str) -> str:
    """心情标签转 emoji（未知返回空串）"""
    return MOOD_EMOJI.get(label, "")


def _is_http(url: str) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


class _ImageFetcher(QThread):
    """后台拉取图像 bytes → QPixmap（避免阻塞 UI 线程）"""
    fetched = Signal(object)   # QPixmap 或 None

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        pm = None
        try:
            r = httpx.get(self._url, timeout=8.0)
            r.raise_for_status()
            img = QImage.fromData(r.content)
            if not img.isNull():
                pm = QPixmap.fromImage(img)
        except Exception:
            pm = None
        self.fetched.emit(pm)


class RichImageWidget(QWidget):
    """图像缩略图：http URL 异步加载显示，stub/失败显示占位；有图时点击放大。"""

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self.url = spec.get("url", "")
        self._fetcher = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.thumb = QLabel()
        self.thumb.setFixedSize(170, 128)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#F0EBE3;border-radius:8px;color:#9A9A9A;font-size:12px;")
        lay.addWidget(self.thumb)
        if _is_http(self.url):
            self.thumb.setText("加载中…")
            self._fetcher = _ImageFetcher(self.url)
            self._fetcher.fetched.connect(self._on_fetched)
            self._fetcher.start()
        else:
            self.thumb.setText("🖼 图像\n(待 provider)")

    def _on_fetched(self, pm):
        if pm is None:
            self.thumb.setText("🖼 图像\n加载失败")
            return
        self._pixmap = pm
        self.thumb.setPixmap(pm.scaled(170, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def mousePressEvent(self, event):
        if self._pixmap is not None:
            from PySide6.QtWidgets import QDialog, QVBoxLayout
            dlg = QDialog(self)
            dlg.setWindowTitle("图像")
            v = QVBoxLayout(dlg)
            lbl = QLabel()
            lbl.setPixmap(self._pixmap)
            v.addWidget(lbl)
            dlg.exec()


class RichAudioWidget(QWidget):
    """语音播放条：http URL 用 QMediaPlayer 播放（▶/⏸ 切换）；stub 显示占位。"""

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.url = spec.get("url", "")
        self._player = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.btn = QPushButton("▶")
        self.btn.setFixedWidth(34)
        self.label = QLabel(f"🎙 语音 · {spec.get('format', '')}")
        self.label.setStyleSheet("color:#9A9A9A;font-size:12px;")
        lay.addWidget(self.btn)
        lay.addWidget(self.label)
        lay.addStretch()
        self._setup_player()

    def _setup_player(self):
        if not _is_http(self.url):
            self.btn.setEnabled(False)
            self.label.setText("🎙 语音(待 provider)")
            return
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self._player = QMediaPlayer()
            self._audio = QAudioOutput()
            self._player.setAudioOutput(self._audio)
            self._player.setSource(QUrl(self.url))
            self.btn.clicked.connect(self._toggle)
        except Exception:
            self.btn.setEnabled(False)
            self.label.setText("🎙 语音(播放器不可用)")
            self._player = None

    def _toggle(self):
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            self.btn.setText("▶")
        else:
            self._player.play()
            self.btn.setText("⏸")
