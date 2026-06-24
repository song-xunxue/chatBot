"""
M6 客户端测试：多模态采集按钮(📎🎙😀)信号、表情包库管理、表情气泡/聊天背景（offscreen）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.2/M6.3 覆盖：采集按钮信号 / StickerManager 导入列出 / add_sticker·set_background
"""
from pathlib import Path


def _fake_img(path: Path) -> None:
    Path(path).write_bytes(b"\x89PNG fake")   # 占位字节


def test_chatview_capture_buttons_and_signals(qapp):
    """📎(图)/🎙(音频)/😀(表情) 按钮就绪，信号可发射"""
    from ui.chat_view import ChatView
    cv = ChatView()
    assert cv.attach.toolTip().startswith("发送图片")
    assert cv.mic.toolTip().startswith("发送语音")
    assert cv.sticker.toolTip() == "表情包"
    fired = {"img": 0, "aud": 0, "stk": 0}
    cv.attach_image.connect(lambda: fired.__setitem__("img", 1))
    cv.attach_audio.connect(lambda: fired.__setitem__("aud", 1))
    cv.sticker_clicked.connect(lambda: fired.__setitem__("stk", 1))
    cv.attach_image.emit(); cv.attach_audio.emit(); cv.sticker_clicked.emit()
    assert fired == {"img": 1, "aud": 1, "stk": 1}


def test_sticker_manager_import_list(tmp_path):
    from ui.stickers import StickerManager
    m = StickerManager(tmp_path / "stickers")
    assert m.list_stickers() == []
    src = tmp_path / "a.png"
    _fake_img(src)
    m.import_file(src)
    assert len(m.list_stickers()) == 1
    m.import_file(src)                      # 重名 → 加序号
    assert len(m.list_stickers()) == 2


def test_chatview_sticker_and_background_no_crash(qapp, tmp_path):
    """add_sticker(空图占位→跳过) 与 set_background 不崩"""
    from ui.chat_view import ChatView
    cv = ChatView()
    img = tmp_path / "s.png"
    _fake_img(img)                          # QPixmap 解析为 null → add_local_image 跳过
    cv.add_sticker(str(img))
    cv.set_background(str(img))
    qapp.processEvents()


def test_main_window_has_sticker_manager_and_handlers(qapp, tmp_path):
    """MainWindow 含 StickerManager 与表情/背景处理方法"""
    from config import ClientConfig
    from ui.main_window import MainWindow
    cfg = ClientConfig(ws_url="ws://127.0.0.1:1/ws", rest_url="http://127.0.0.1:1",
                       token="t", object_id="t", db_path=tmp_path / "chat.db", message_limit=50)
    win = MainWindow(cfg)
    assert hasattr(win, "stickers")
    assert callable(win._on_pick_sticker)   # V1.1 M14：去设置入口，保留表情
    assert hasattr(win, "object_list")      # V1.1 M14 微信式左对象列表
    win.close()
    qapp.processEvents()
