"""
V1.1 M14 客户端交互测试（P0-5）：对象切换清空+重载 / 空状态 / 桌宠仅回复时抖动语义。
守护此前 UI 层裸奔的关键路径（审查 ww19vp317 P0-5）。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. V1.2 补 M14 交互测试：_on_select_object/chat.clear/空状态/ai_done shake 触发与抑制
"""
from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem


def _make_win(qapp, tmp_path, mock_ws, pet=None):
    """构造 MainWindow（mock_ws 不真起 WS 线程，pet 可选 mock）"""
    from config import ClientConfig
    from ui.main_window import MainWindow
    cfg = ClientConfig(
        ws_url="ws://127.0.0.1:1/ws", rest_url="http://127.0.0.1:1",
        token="t", object_id="t", db_path=tmp_path / "chat.db", message_limit=50,
    )
    return MainWindow(cfg, pet=pet)


def test_empty_state_when_no_personas(qapp, tmp_path, mock_ws):
    """无对象时 object_list 为空（_show_empty_hint 时机修复后，拉取前不再误报）"""
    win = _make_win(qapp, tmp_path, mock_ws)   # REST 127.0.0.1:1 失败 → personas=[]
    qapp.processEvents()
    assert win.object_list.count() == 0
    win.close()
    qapp.processEvents()


def test_ai_done_with_text_triggers_shake(qapp, tmp_path, mock_ws):
    """V1.1 M14：收到回复(ai_done 有 text) → 桌宠抖动"""
    pet = MagicMock()
    win = _make_win(qapp, tmp_path, mock_ws, pet=pet)
    win._on_msg({"type": "ai_start", "payload": {}})
    win._on_msg({"type": "ai_done", "payload": {"text": "嗨"}})
    qapp.processEvents()
    pet.shake.assert_called_once()
    win.close()
    qapp.processEvents()


def test_ai_done_held_or_empty_no_shake(qapp, tmp_path, mock_ws):
    """V1.1 M14：held/空回复 → 不抖动（仅真正回复才抖）"""
    pet = MagicMock()
    win = _make_win(qapp, tmp_path, mock_ws, pet=pet)
    win._on_msg({"type": "ai_start", "payload": {}})
    win._on_msg({"type": "ai_done", "payload": {"text": "", "held": True}})
    qapp.processEvents()
    pet.shake.assert_not_called()
    win.close()
    qapp.processEvents()


def test_proactive_msg_triggers_shake(qapp, tmp_path, mock_ws):
    """主动消息带 nudge → 桌宠抖动"""
    pet = MagicMock()
    win = _make_win(qapp, tmp_path, mock_ws, pet=pet)
    win._on_msg({"type": "proactive_msg", "payload": {"text": "在吗", "nudge": True}})
    qapp.processEvents()
    pet.shake.assert_called_once()
    win.close()
    qapp.processEvents()


def test_select_object_switches_oid(qapp, tmp_path, mock_ws):
    """V1.1 M14：点击对象 → cfg.object_id 切换 + 标题更新（chat.clear 在 ChatView.clear 已测）"""
    win = _make_win(qapp, tmp_path, mock_ws)
    item = QListWidgetItem("清浔")
    item.setData(Qt.UserRole, "qingxun")
    win.object_list.addItem(item)
    win._on_select_object(item)
    qapp.processEvents()
    assert win.cfg.object_id == "qingxun"
    assert win.title.text() == "清浔"
    win.close()
    qapp.processEvents()


def test_select_same_object_noop(qapp, tmp_path, mock_ws):
    """点击当前已选对象 → 不重复切换"""
    win = _make_win(qapp, tmp_path, mock_ws)   # cfg.object_id == "t"
    item = QListWidgetItem("t")
    item.setData(Qt.UserRole, "t")
    win.object_list.addItem(item)
    win._on_select_object(item)
    qapp.processEvents()
    assert win.cfg.object_id == "t"   # 未变
    win.close()
    qapp.processEvents()
