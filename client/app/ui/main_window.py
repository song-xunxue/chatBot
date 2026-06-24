"""
主窗口（V1.1 M14 微信式）：左侧聊天对象列表 + 右侧聊天区，接线 WS/REST/Store。
按用户决策5 简化为纯聊天：去除人设管理/设置入口（人设 CRUD 在服务端面板），
只留聊天 + 多模态收发(表情/附件/语音)；无对象时提示去面板添加；长方形窗口。
桌宠仅"收到回复时抖动"（ai_done/proactive 触发，去闲置弹跳在 pet_window 处理）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建主窗口：顶栏/抽屉/聊天区 + WS·REST·Store 接线
  2. V1.1 M14 微信式重构：左对象列表常驻 + 右聊天，去 ☰抽屉/⚙设置/心情顶栏，
     对象点击切换 object_id，ai_done 收到回复时桌宠抖动，空状态提示去面板添加

2026-06-25
变更说明：
  1. 微信/QQ 风格 UI：左列表项=圆形头像+名称(自定义 widget)；顶栏=头像+名称+在线点，
     去右侧异常空白；气泡/左列表头像从人设 avatar 拉取(缓存)，失败回退默认 svg
  2. 新增用户头像：顶栏"我"头像按钮选图 → 存 client/data/user_avatar.png → 重载
  3. 输入栏图标改 SVG（smile/clip/mic）
"""
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from config import PROJECT_ROOT, ClientConfig
from net.ws_client import WSClient
from net.rest_client import RestClient
from store.db import ChatStore
from ui.chat_view import ChatView
from ui.stickers import StickerPickerDialog, StickerManager
from shared.protocol import now_ts

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent                  # client/app/ui
_DEFAULT_AVATAR_SVG = str(_HERE / "avatar_default.svg")
_USER_AVATAR_SVG = str(_HERE / "avatar_user_default.svg")
_USER_AVATAR_PATH = PROJECT_ROOT / "client" / "data" / "user_avatar.png"
_AVATAR_PX = 40
_TOPBAR_AVATAR_PX = 32


def _circular_pixmap(pm: QPixmap, size: int = _AVATAR_PX) -> QPixmap:
    """把任意 pixmap 裁成正方形并加圆形遮罩（微信圆形头像）。"""
    if pm.isNull():
        return pm
    # 先等比裁正方形（取中心）
    side = min(pm.width(), pm.height())
    cropped = pm.copy((pm.width() - side) // 2, (pm.height() - side) // 2, side, side)
    scaled = cropped.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    from PySide6.QtGui import QPainter, QBitmap, QRegion
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    mask = QBitmap(size, size)
    mask.fill(Qt.color0)
    p = QPainter(mask)
    p.setBrush(Qt.color1)
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, size, size)         # 圆形遮罩
    p.end()
    out.setMask(mask)
    painter = QPainter(out)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return out


def _pixmap_from_bytes(data: bytes) -> QPixmap:
    """字节 → QPixmap（失败返回 null pixmap）"""
    pm = QPixmap()
    pm.loadFromData(data)
    return pm


def _pixmap_from_svg(svg_path: str, size: int = _AVATAR_PX) -> QPixmap:
    """SVG → QPixmap（用 SVG renderer 渲染指定尺寸）"""
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtGui import QImage, QPainter
    renderer = QSvgRenderer(svg_path)
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    renderer.render(p)
    p.end()
    return QPixmap.fromImage(img)


class _ObjectListItem(QWidget):
    """左列表单项 widget：圆形头像(40) + 名称(14px 600)"""

    def __init__(self, name: str, avatar_pm: QPixmap | None = None, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)
        self.avatar = QLabel()
        self.avatar.setFixedSize(_AVATAR_PX, _AVATAR_PX)
        self._set_avatar(avatar_pm)
        self.name = QLabel(name)
        self.name.setObjectName("objectName")
        self.name.setStyleSheet("font-size: 14px; font-weight: 600;")
        h.addWidget(self.avatar)
        h.addWidget(self.name, 1)

    def _set_avatar(self, pm: QPixmap | None):
        if pm is not None and not pm.isNull():
            self.avatar.setPixmap(pm.scaled(
                _AVATAR_PX, _AVATAR_PX, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        else:
            self.avatar.setPixmap(_pixmap_from_svg(_DEFAULT_AVATAR_SVG, _AVATAR_PX))


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

        # 头像缓存：pid -> 圆形 QPixmap（人设头像，避免重复拉取）
        self._persona_avatar_cache: dict[str, QPixmap] = {}
        # 当前选中对象的头像（气泡用）
        self._current_assistant_avatar: QPixmap | None = None
        # 用户头像
        self._user_avatar: QPixmap | None = None

        self._build_ui()
        self._wire()
        self._load_user_avatar()
        self._load_personas()    # 先拉人设头像（设 _current_assistant_avatar），历史消息才有头像
        self._load_history()
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
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(8)
        # 当前对象头像（32×32 圆形）
        self.topbar_avatar = QLabel()
        self.topbar_avatar.setFixedSize(_TOPBAR_AVATAR_PX, _TOPBAR_AVATAR_PX)
        self.topbar_avatar.setPixmap(_pixmap_from_svg(_DEFAULT_AVATAR_SVG, _TOPBAR_AVATAR_PX))
        self.title = QLabel("选择一个聊天对象开始")
        self.title.setObjectName("title")
        # 在线状态点
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("status")
        self.status_dot.setStyleSheet("color: #BFBFBF; font-size: 11px;")  # 离线灰
        self.status_text = QLabel("离线")
        self.status_text.setObjectName("status")
        # 紧凑布局：头像 + 标题 + 状态点 + 状态文字 + 弹簧 + "我"头像按钮
        h.addWidget(self.topbar_avatar)
        h.addWidget(self.title)
        h.addSpacing(4)
        h.addWidget(self.status_dot)
        h.addWidget(self.status_text)
        h.addStretch()
        # "我"头像按钮（用户头像设置入口）
        self.me_btn = QPushButton()
        self.me_btn.setObjectName("meBtn")
        self.me_btn.setFixedSize(_TOPBAR_AVATAR_PX, _TOPBAR_AVATAR_PX)
        self.me_btn.setToolTip("点击设置我的头像")
        self.me_btn.setCursor(Qt.PointingHandCursor)
        self.me_btn.clicked.connect(self._on_pick_user_avatar)
        h.addWidget(self.me_btn)
        return bar

    def _show_empty_hint(self):
        """无对象或未选中时，聊天区提示去面板添加"""
        if self.object_list.count() == 0:
            self.chat.add_system("暂无聊天对象，请到管理面板（http://43.140.219.99:8000/）添加")

    # —— 头像加载 ——
    def _load_persona_avatar(self, pid: str, persona: dict) -> QPixmap | None:
        """拉人设头像（缓存）：persona.avatar 为相对路径 → GET rest_url/avatar。
        失败/无则返回 None（调用方用默认 svg）。"""
        if pid in self._persona_avatar_cache:
            return self._persona_avatar_cache[pid]
        pm: QPixmap | None = None
        avatar_rel = (persona or {}).get("avatar") or ""
        if avatar_rel:
            try:
                data = self.rest.get_avatar_bytes(avatar_rel)
                if data:
                    pm = _circular_pixmap(_pixmap_from_bytes(data), _AVATAR_PX)
                    if pm.isNull():
                        pm = None
            except Exception as e:
                logger.debug("load persona avatar failed pid=%s err=%s", pid, e)
        # 缓存（None 也缓存，避免反复请求失败）
        self._persona_avatar_cache[pid] = pm
        return pm

    def _load_user_avatar(self):
        """加载用户头像（client/data/user_avatar.png）；无则默认 svg（绿色头像）"""
        pm: QPixmap | None = None
        p = Path(self.cfg.user_avatar) if getattr(self.cfg, "user_avatar", "") else _USER_AVATAR_PATH
        if p and p.exists():
            pm = _circular_pixmap(QPixmap(str(p)), _AVATAR_PX)
            if pm.isNull():
                pm = None
        if pm is None:
            pm = _circular_pixmap(_pixmap_from_svg(_USER_AVATAR_SVG, _AVATAR_PX), _AVATAR_PX)
        self._user_avatar = pm
        # 同步顶栏"我"按钮图标
        if hasattr(self, "me_btn"):
            self.me_btn.setIcon(QPixmap(pm).scaled(
                _TOPBAR_AVATAR_PX, _TOPBAR_AVATAR_PX,
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            self.me_btn.setIconSize(self.me_btn.size())

    def _on_pick_user_avatar(self):
        """顶栏"我"头像按钮：选图 → 存 client/data/user_avatar.png → 重载头像"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择我的头像", "", "图片 (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        try:
            _USER_AVATAR_PATH.parent.mkdir(parents=True, exist_ok=True)
            _USER_AVATAR_PATH.write_bytes(Path(path).read_bytes())
            self.cfg.user_avatar = str(_USER_AVATAR_PATH)
        except Exception as e:
            self.chat.add_system(f"⚠ 头像保存失败: {e}")
            return
        self._load_user_avatar()

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
            self.chat.add_message(m.role, m.text, ts=m.ts,
                                  avatar_pixmap=self._avatar_for_role(m.role))

    def _avatar_for_role(self, role: str) -> QPixmap | None:
        """按角色取气泡头像：assistant=当前对象人设头像，user=用户头像"""
        if role == "user":
            return self._user_avatar
        return self._current_assistant_avatar

    def _load_personas(self):
        """从服务端拉人设作为聊天对象，填入左列表（item widget = 头像+名称，带 persona_id）"""
        self.object_list.clear()
        try:
            personas = self.rest.list_personas()
        except Exception as e:
            logger.debug("load personas failed: %s", e)
            personas = []
        self._persona_by_id: dict[str, dict] = {p.get("id", ""): p for p in personas}
        for p in personas:
            pid = p.get("id", "")
            name = p.get("name") or pid
            avatar_pm = self._load_persona_avatar(pid, p)
            widget = _ObjectListItem(name, avatar_pm)
            item = QListWidgetItem(self.object_list)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, pid)
            self.object_list.addItem(item)
            self.object_list.setItemWidget(item, widget)
        # 默认选中当前 object_id 对应项
        for i in range(self.object_list.count()):
            it = self.object_list.item(i)
            if it.data(Qt.UserRole) == self.cfg.object_id:
                self.object_list.setCurrentRow(i)
                self._apply_selected_persona(it)
                break
        self._show_empty_hint()

    def _apply_selected_persona(self, item: QListWidgetItem):
        """选中某对象后：更新顶栏头像/标题 + 当前 assistant 气泡头像"""
        pid = item.data(Qt.UserRole)
        persona = self._persona_by_id.get(pid, {})
        # 名称优先级：人设 name → 列表项文本(测试/手动添加场景) → pid
        name = persona.get("name") or item.text() or pid
        self.title.setText(name)
        pm = self._persona_avatar_cache.get(pid)
        top_pm = pm if pm is not None else _pixmap_from_svg(_DEFAULT_AVATAR_SVG, _TOPBAR_AVATAR_PX)
        self.topbar_avatar.setPixmap(top_pm.scaled(
            _TOPBAR_AVATAR_PX, _TOPBAR_AVATAR_PX,
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        self._current_assistant_avatar = pm

    def _on_select_object(self, item):
        """点击左列表对象 → 切换当前 object_id（WS 后续消息对象 + 重载历史）"""
        pid = item.data(Qt.UserRole) or item.text()
        if not pid or pid == self.cfg.object_id:
            return
        self.cfg.object_id = pid
        if hasattr(self.ws, "object_id"):
            self.ws.object_id = pid          # WS 后续 user_msg 带新对象
        self._apply_selected_persona(item)
        # 清空聊天区 + 重载该对象历史
        self.chat.clear()
        self._load_history()

    def _set_online(self, on: bool):
        self._online = on
        self.status_dot.setStyleSheet(
            f"color: {'#07C160' if on else '#BFBFBF'}; font-size: 11px;")
        self.status_text.setText("在线" if on else "离线")

    # —— 发送 ——
    def _on_send(self, text: str):
        self.chat.add_message("user", text, ts=now_ts(), avatar_pixmap=self._user_avatar)
        self.store.append_message(self.cfg.object_id, "user", text, ts=now_ts())
        if self._online:
            self.ws.send_text(text)
        else:
            self.store.enqueue_outbox(self.cfg.object_id, text, ts=now_ts())
            self.chat.add_system("（离线，消息将在重连后发送）")

    def _on_pick_image(self):
        """附件：选图 → 视觉理解 → 描述填入输入栏"""
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
        """语音：选音频 → 语音识别 → 转写填入输入栏"""
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
        """表情：打开表情包选择器；选中 → 发表情气泡"""
        dlg = StickerPickerDialog(self.stickers, self)
        dlg.picked.connect(self._send_sticker)
        dlg.exec()

    def _send_sticker(self, path: str):
        self.chat.add_sticker(path, avatar_pixmap=self._user_avatar)
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
            self._streaming = self.chat.start_ai_bubble(avatar_pixmap=self._current_assistant_avatar)
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
                self.chat.add_message("assistant", text, ts=now_ts(), rich=rich,
                                      avatar_pixmap=self._current_assistant_avatar)
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
            self.chat.add_message("assistant", text, ts=now_ts(),
                                  avatar_pixmap=self._current_assistant_avatar)
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
