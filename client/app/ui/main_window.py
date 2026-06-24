"""
主窗口：顶栏 + 抽屉(人设/状态) + 聊天视图，接线 WS/REST/Store。
温暖拟人化 + 单列 + 抽屉布局。WS 收到的消息驱动 ChatView 流式渲染并落 SQLite；
离线发送入 outbox，重连自动补发。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建主窗口：顶栏/抽屉/聊天区 + WS·REST·Store 接线 + 流式/离线/重连补发
"""
import logging

from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QPushButton, QVBoxLayout, QWidget,
)

from config import PROJECT_ROOT, ClientConfig
from net.ws_client import WSClient
from net.rest_client import RestClient
from store.db import ChatStore
from ui.chat_view import ChatView
from ui.rich_widgets import mood_emoji
from ui.stickers import StickerPickerDialog, StickerManager
from shared.protocol import now_ts

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """主窗口：单列聊天 + 可切换抽屉"""

    def __init__(self, config: ClientConfig, pet: "object | None" = None):
        super().__init__()
        self.cfg = config
        self.pet = pet                          # 桌宠引用（nudge 抖动 / 关闭缩到桌宠）
        self._force_close = False               # 托盘退出时置 True，绕过"缩到桌宠"
        self.setWindowTitle("MyChat · 小聊")
        self.resize(400, 640)
        self._streaming = None
        self._online = False
        self.store = ChatStore(config.db_path, config.message_limit)
        self.rest = RestClient(config.rest_url, config.token)
        self.ws = WSClient(config.ws_url, config.token, config.object_id)
        self.stickers = StickerManager(PROJECT_ROOT / "client" / "data" / "stickers")

        self._build_ui()
        self._wire()
        self._load_history()
        self._load_personas()
        self.ws.start()

    # —— UI 构建 ——
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.drawer = self._build_drawer()
        self.drawer.setFixedWidth(190)
        self.drawer.setVisible(False)
        outer.addWidget(self.drawer)
        col = QWidget()
        cl = QVBoxLayout(col)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._build_topbar())
        self.chat = ChatView()
        cl.addWidget(self.chat, 1)
        outer.addWidget(col, 1)

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(48)
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 0, 8, 0)
        h.setSpacing(8)
        self.btn_menu = QPushButton("☰")
        self.btn_menu.setObjectName("iconBtn")
        self.btn_menu.setToolTip("人设/历史/设置")
        self.btn_menu.clicked.connect(self._toggle_drawer)
        self.title = QLabel("小聊")
        self.title.setObjectName("title")
        self.mood = QLabel("")                       # 心情占位（多模态阶段接入）
        self.dot = QLabel("●离线")
        self.dot.setObjectName("muted")
        self.btn_set = QPushButton("⚙")
        self.btn_set.setObjectName("iconBtn")
        self.btn_set.setToolTip("设置聊天背景")
        self.btn_set.clicked.connect(self._on_set_background)
        h.addWidget(self.btn_menu)
        h.addWidget(self.title)
        h.addStretch()
        h.addWidget(self.mood)
        h.addWidget(self.dot)
        h.addWidget(self.btn_set)
        return bar

    def _build_drawer(self):
        f = QFrame()
        f.setObjectName("drawer")
        v = QVBoxLayout(f)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        t = QLabel("人设")
        t.setObjectName("title")
        v.addWidget(t)
        self.persona_list = QListWidget()
        v.addWidget(self.persona_list, 1)
        self.drawer_status = QLabel("●离线")
        self.drawer_status.setObjectName("muted")
        v.addWidget(self.drawer_status)
        return f

    # —— 接线 ——
    def _wire(self):
        self.chat.send_text.connect(self._on_send)
        self.chat.attach_image.connect(self._on_pick_image)
        self.chat.attach_audio.connect(self._on_pick_audio)
        self.chat.sticker_clicked.connect(self._on_pick_sticker)
        self.ws.msg_received.connect(self._on_msg)
        self.ws.connected.connect(self._on_connected)
        self.ws.disconnected.connect(self._on_disconnected)
        self.ws.error_occurred.connect(lambda e: self.chat.add_system(f"⚠ {e}"))

    def _load_history(self):
        for m in self.store.get_messages(self.cfg.object_id):
            self.chat.add_message(m.role, m.text, ts=m.ts)

    def _load_personas(self):
        try:
            for p in self.rest.list_personas():
                self.persona_list.addItem(p.get("name") or p.get("id", ""))
        except Exception as e:
            logger.debug("load personas failed: %s", e)   # 离线/无服务端时静默

    def _toggle_drawer(self):
        self.drawer.setVisible(not self.drawer.isVisible())

    def _set_online(self, on: bool):
        self._online = on
        txt = "●在线" if on else "●离线"
        self.dot.setText(txt)
        self.drawer_status.setText(txt)

    def _apply_state(self, state: dict):
        """应用 ai_done 携带的状态：心情 → 顶栏 emoji"""
        mood = state.get("mood")
        if mood:
            self.mood.setText(mood_emoji(mood))
            self.mood.setToolTip(f"心情：{mood}")

    # —— 发送 ——
    def _on_send(self, text: str):
        self.chat.add_message("user", text, ts=now_ts())
        self.store.append_message(self.cfg.object_id, "user", text, ts=now_ts())
        if self._online:
            self.ws.send_text(text)
        else:
            self.store.enqueue_outbox(self.cfg.object_id, text, ts=now_ts())
            self.chat.add_system("（离线，消息将在重连后发送）")

    def _on_pick_image(self):
        """📎：选图 → 视觉理解 → 描述填入输入栏（用户可编辑后发送）"""
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        low = path.lower()
        mime = "image/png" if low.endswith(".png") else ("image/webp" if low.endswith(".webp") else "image/jpeg")
        try:
            with open(path, "rb") as f:
                data = f.read()
            desc = self.rest.vision(data, prompt="请简要描述这张图片的内容，便于对话参考", mime=mime)
        except Exception as e:
            self.chat.add_system(f"⚠ 图像理解失败: {e}")
            return
        self.chat.input.setText(f"（图片：{desc}）" + self.chat.input.text())

    def _on_pick_audio(self):
        """🎙：选音频 → 语音识别 → 转写填入输入栏"""
        path, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "音频 (*.wav *.mp3 *.m4a)")
        if not path:
            return
        ext = path.rsplit(".", 1)[-1].lower()
        try:
            with open(path, "rb") as f:
                data = f.read()
            text = self.rest.asr(data, fmt=ext)
        except Exception as e:
            self.chat.add_system(f"⚠ 语音识别失败: {e}")
            return
        self.chat.input.setText(text + self.chat.input.text())

    def _on_pick_sticker(self):
        """😀：打开表情包选择器；选中 → 发表情气泡"""
        dlg = StickerPickerDialog(self.stickers, self)
        dlg.picked.connect(self._send_sticker)
        dlg.exec()

    def _send_sticker(self, path: str):
        self.chat.add_sticker(path)
        self.store.append_message(self.cfg.object_id, "user", "[表情包]", ts=now_ts())

    def _on_set_background(self):
        """⚙：选择聊天背景图"""
        path, _ = QFileDialog.getOpenFileName(self, "选择聊天背景", "", "图片 (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.chat.set_background(path)

    def _on_connected(self):
        self._set_online(True)
        self.chat.add_system("已连接服务端")
        # 重连补发：把离线期间入队的消息逐条发出并标记
        for row in self.store.pending_outbox(self.cfg.object_id):
            self.ws.send_text(row["text"])
            self.store.mark_outbox_sent(row["id"])

    def _on_disconnected(self):
        self._set_online(False)

    # —— 收消息：驱动流式渲染 + 落库 ——
    def _on_msg(self, data: dict):
        t = data.get("type")
        payload = data.get("payload", {})
        if t == "ai_start":
            self._streaming = self.chat.start_ai_bubble()
        elif t == "ai_chunk":
            self.chat.append_chunk(self._streaming, payload.get("delta", {}).get("text", ""))
        elif t == "ai_done":
            text = payload.get("text", "")
            held = bool(payload.get("held"))
            rich = payload.get("rich") or {}
            self._apply_state(payload.get("state") or {})   # 心情等状态 → 顶栏
            if self._streaming is not None:
                self.chat.finalize_ai(self._streaming, text, held=held, rich=rich)
                if not held and text:
                    self.store.append_message(self.cfg.object_id, "assistant", text, ts=now_ts())
            elif text:                                    # 无流式气泡但有文本（插件自产回复）
                self.chat.add_message("assistant", text, ts=now_ts(), rich=rich)
                self.store.append_message(self.cfg.object_id, "assistant", text, ts=now_ts())
            self._streaming = None
        elif t == "error":
            self.chat.add_system(payload.get("message", "错误"))
        elif t == "proactive_msg":
            text = payload.get("text", "")
            self.chat.add_system("💬 对方主动发来消息")     # 主动消息提示
            self.chat.add_message("assistant", text, ts=now_ts())
            self.store.append_message(self.cfg.object_id, "assistant", text, ts=now_ts())
            if payload.get("nudge") and self.pet is not None:
                self.pet.shake()                              # 桌宠抖动（M6.1）

    def closeEvent(self, event):
        # 有桌宠且非强制退出：关闭聊天窗 → 缩到桌宠（不退出，WS/Store 保留）
        if self.pet is not None and not self._force_close:
            event.ignore()
            self.hide()
            return
        try:
            self.ws.quit()
            self.ws.wait(2000)
        finally:
            self.store.close()
        super().closeEvent(event)

    def real_close(self):
        """真正退出（托盘退出调用）：绕过"缩到桌宠"，执行真实关闭"""
        self._force_close = True
        self.close()
