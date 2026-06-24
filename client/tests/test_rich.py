"""
富内容组件测试：心情 emoji 映射、stub 图像占位、气泡富内容渲染（offscreen）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 多模态：覆盖 mood_emoji / RichImageWidget(stub) / BubbleRow.add_rich
"""


def test_mood_emoji_mapping():
    from ui.rich_widgets import mood_emoji
    assert mood_emoji("开心") == "😊"
    assert mood_emoji("愉悦") == "🙂"
    assert mood_emoji("平静") == "😐"
    assert mood_emoji("低落") == "😕"
    assert mood_emoji("难过") == "😢"
    assert mood_emoji("未知") == ""


def test_rich_image_stub_shows_placeholder(qapp):
    """stub:// URL → 占位（不启动网络抓取）"""
    from ui.rich_widgets import RichImageWidget
    w = RichImageWidget({"url": "stub://img/123", "provider": "stub"})
    qapp.processEvents()
    assert w.thumb.text().startswith("🖼")
    assert w._fetcher is None            # stub 不启动抓取线程


def test_rich_audio_stub_disabled(qapp):
    """stub:// 音频 → 播放按钮禁用 + 占位"""
    from ui.rich_widgets import RichAudioWidget
    w = RichAudioWidget({"url": "stub://tts/abc", "format": "mp3"})
    qapp.processEvents()
    assert w.btn.isEnabled() is False
    assert w._player is None


def test_bubble_renders_rich(qapp):
    """气泡渲染文本 + 图像/语音富内容（stub 占位），不崩"""
    from ui.chat_view import BubbleRow
    row = BubbleRow("assistant", "看这只猫", ts=1)
    row.add_rich({"image": [{"url": "stub://img/x"}], "audio": [{"url": "stub://tts/y"}]})
    qapp.processEvents()
    assert row.bubble.text() == "看这只猫"


def test_main_window_applies_mood_state(qapp, tmp_path):
    """MainWindow 收到带 state.mood 的 ai_done → 顶栏心情 emoji 更新"""
    from config import ClientConfig
    from ui.main_window import MainWindow
    cfg = ClientConfig(
        ws_url="ws://127.0.0.1:1/ws", rest_url="http://127.0.0.1:1",
        token="t", object_id="t", db_path=tmp_path / "chat.db", message_limit=50,
    )
    win = MainWindow(cfg)
    win._on_msg({"type": "ai_done", "payload": {"text": "嗨", "state": {"mood": "开心"}}})
    qapp.processEvents()
    assert win.mood.text() == "😊"
    win.close()
    qapp.processEvents()
