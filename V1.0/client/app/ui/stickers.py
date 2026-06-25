"""
表情包库（M6.3）：本地导入/列出/选用，存于 client/data/stickers/。
StickerManager 管理文件；StickerPickerDialog 网格选择 + 导入。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.3 创建表情包库：管理 + 选择对话框
"""
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QDialog,
)


class StickerManager:
    """本地表情包文件管理（client/data/stickers/）"""

    def __init__(self, base_dir):
        self.dir = Path(base_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def list_stickers(self) -> list[Path]:
        out: list[Path] = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"):
            out.extend(self.dir.glob(ext))
        return sorted(out)

    def import_file(self, src) -> Path:
        """复制一个图片到表情包目录（重名自动加序号），返回目标路径"""
        src = Path(src)
        dst = self.dir / src.name
        i = 1
        while dst.exists():
            dst = self.dir / f"{src.stem}_{i}{src.suffix}"
            i += 1
        shutil.copyfile(src, dst)
        return dst


class _StickerThumb(QLabel):
    """单个表情包缩略图，可点击"""
    clicked = Signal()

    def __init__(self, path: str):
        super().__init__()
        self.setFixedSize(82, 82)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border:1px solid #ECE6DE;border-radius:6px;background:#FFF;")
        pm = QPixmap(path)
        if not pm.isNull():
            self.setPixmap(pm.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def mousePressEvent(self, event):
        self.clicked.emit()


class StickerPickerDialog(QDialog):
    """表情包选择对话框：网格展示 + 导入；点选发射 picked(path)"""
    picked = Signal(str)

    def __init__(self, manager: StickerManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("表情包")
        self.resize(380, 320)
        self.mgr = manager
        v = QVBoxLayout(self)
        self._grid_host = QWidget()
        self.grid = QGridLayout(self._grid_host)
        v.addWidget(self._grid_host, 1)
        self.hint = QLabel("")
        self.hint.setObjectName("muted")
        self.hint.setAlignment(Qt.AlignCenter)
        v.addWidget(self.hint)
        bar = QHBoxLayout()
        btn_import = QPushButton("导入表情包")
        btn_import.setObjectName("sendBtn")
        btn_import.clicked.connect(self._import)
        bar.addStretch()
        bar.addWidget(btn_import)
        v.addLayout(bar)
        self._refresh()

    def _refresh(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        stickers = self.mgr.list_stickers()
        self.hint.setText("还没有表情包，点【导入表情包】添加" if not stickers else "")
        cols = 4
        for idx, p in enumerate(stickers):
            thumb = _StickerThumb(str(p))
            thumb.clicked.connect(lambda path=str(p): self._pick(path))
            self.grid.addWidget(thumb, idx // cols, idx % cols)

    def _import(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "导入表情包", "",
                                                "图片 (*.png *.jpg *.jpeg *.gif *.webp)")
        for p in paths:
            self.mgr.import_file(p)
        self._refresh()

    def _pick(self, path: str):
        self.picked.emit(path)
        self.accept()
