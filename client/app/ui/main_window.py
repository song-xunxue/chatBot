"""
主窗口（V1.1 M14 微信式）：左侧聊天对象列表 + 右侧聊天区，接线 WS/REST/Store。
按用户决策5 简化为纯聊天：去除人设管理/设置入口（人设 CRUD 在服务端面板），
只留聊天 + 多模态收发(📎/🎙/😀)；无对象时提示去面板添加；温馨长方形窗口。
桌宠仅"收到回复时抖动"（ai_done/proactive 触发，去闲置弹跳在 pet_window 处理）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建主窗口：顶栏/抽屉/聊天区 + WS·REST·Store 接线
  2. V1.1 M14 微信式重构：左对象列表常驻 + 右聊天，去 ☰抽屉/⚙设置/心情顶栏，
     对象点击切换 object_id，ai_done 收到回复时桌宠抖动，空状态提示去面板添加
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow,
    QSplitter, QVBoxLayout, QWidget,
)

from config import PROJECT_ROOT, ClientConfig
from net.ws_client import WSClient
from net.rest_client import RestClient
from store.db import ChatStore
from ui.chat_view import ChatView
from ui.stickers import StickerPickerDialog, StickerManager
from shared.protocol import now_ts

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """主窗口（微信式）：左聊天对象列表 + 右聊天区"""

    def __init__(self, config: ClientConfig, pet: "object | None" = None):
        super().__init__()
        self.cfg = config
        self.pet = pet                          # 桌宠引用（仅收到回复时抖动）
        self._force_close = False               # 托盘退出时置 True，绕过"缩到桌宠"
        self.setWindowTitle("MyChat · 小聊")
        self.resize(960, 640)                   # V1.1 M14 长方形窗口
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

        split = QSplitter(Qt.Horizontal)
        # 左：聊天对象列表（常驻，微信式）
        left = QFrame()
        left.setObjectName("objectPanel")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        head = QLabel("聊天对象")
        head.setObjectName("panelHead")
        head.setFixedHeight(40)
        lv.addWidget(head)
        self.object_list = QListWidget()
        self.object_list.setObjectName("objectList")
        self.object_list.itemClicked.connect(self._on_select_object)
        lv.addWidget(self.object_list, 1)
        # 右：顶栏 + 聊天
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self._build_topbar())
        self.chat = ChatView()
        rv.addWidget(self.chat, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 700])
        split.setCollapsible(0, False)
        outer.addWidget(split)
        # 空状态提示由 _load_personas 末尾按实际对象数判断（避免拉取前误报"暂无"）

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(48)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 12, 0)
        h.setSpacing(8)
        self.title = QLabel("选择一个聊天对象开始")
        self.title.setObjectName("title")
        self.dot = QLabel("●离线")
        self.dot.setObjectName("muted")
        h.addWidget(self.title)
        h.addStretch()
        h.addWidget(self.dot)
        return bar

    def _show_empty_hint(self):
        """无对象或未选中时，聊天区提示去面板添加"""
        if self.object_list.count() == 0:
            self.chat.add_system("暂无聊天对象，请到管理面板（http://43.140.219.99:8000/）添加")

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
        """从服务端拉人设作为聊天对象，填入左列表（item 带 persona_id）"""
        self.object_list.clear()
        try:
            personas = self.rest.list_personas()
        except Exception as e:
            logger.debug("load personas failed: %s", e)
            personas = []
        for p in personas:
            pid = p.get("id", "")
            name = p.get("name") or pid
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, pid)
            self.object_list.addItem(item)
        # 默认选中当前 object_id 对应项
        for i in range(self.object_list.count()):
            if self.object_list.item(i).data(Qt.UserRole) == self.cfg.object_id:
                self.object_list.setCurrentRow(i)
                self.title.setText(self.object_list.item(i).text())
                break
        self._show_empty_hint()

    def _on_select_object(self, item):
        """点击左列表对象 → 切换当前 object_id（WS 后续消息对象 + 重载历史）"""
        pid = item.data(Qt.UserRole) or item.text()
        if not pid or pid == self.cfg.object_id:
            return
        self.cfg.object_id = pid
        if hasattr(self.ws, "object_id"):
            self.ws.object_id = pid          # WS 后续 user_msg 带新对象
        self.title.setText(item.text())
        # 清空聊天区 + 重载该对象历史
        self.chat.clear()
        self._load_history()

    def _set_online(self, on: bool):
        self._online = on
        self.dot.setText("●在线" if on else "●离线")

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
        """📎：选图 → 视觉理解 → 描述填入输入栏"""
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        low = path.lower()
        mime = "image/png" if low.endswith(".png") else ("image/webm" if low.endswith(".webp") else "image/jpeg")
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
            if self._streaming is not None:
                self.chat.finalize_ai(self._streaming, text, held=held, rich=rich)
                if not held and text:
                    self.store.append_message(self.cfg.object_id, "assistant", text, ts=now_ts())
            elif text:                                    # 无流式气泡但有文本（插件自产回复）
                self.chat.add_message("assistant", text, ts=now_ts(), rich=rich)
                self.store.append_message(self.cfg.object_id, "assistant", text, ts=now_ts())
            self._streaming = None
            # V1.1 M14：仅收到回复时桌宠抖动（去闲置弹跳）
            if not held and text and self.pet is not None and hasattr(self.pet, "shake"):
                self.pet.shake()
        elif t == "error":
            self.chat.add_system(payload.get("message", "错误"))
        elif t == "proactive_msg":
            text = payload.get("text", "")
            self.chat.add_system("💬 对方主动发来消息")
            self.chat.add_message("assistant", text, ts=now_ts())
            self.store.append_message(self.cfg.object_id, "assistant", text, ts=now_ts())
            if payload.get("nudge") and self.pet is not None and hasattr(self.pet, "shake"):
                self.pet.shake()
        elif t == "takeover_pending":                         # V1.1 M13 代答等待态
            self.chat.add_system("⏳ 等待人工代答…")
        elif t == "takeover_timeout":                         # V1.1 M13 代答超时
            self.chat.add_system("代人超时，请重试")
            self._streaming = None

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
