"""
UI 冒烟测试（QT_QPA_PLATFORM=offscreen）：验证主题加载、气泡/流式渲染不崩。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建 UI 冒烟：主题 + ChatView 渲染

2026-06-25
变更说明：
  1. 适配微信/QQ 风格主题：断言改为微信绿 USER_GREEN + 列表/气泡 objectName
"""


def test_theme_qss_loads():
    from ui.theme import QSS, USER_GREEN
    assert "95EC69" in QSS                    # 微信绿注入（用户气泡/发送按钮）
    assert "border-radius" in QSS
    assert USER_GREEN == "#95EC69"


def test_chatview_renders_messages_and_streaming(qapp):
    from ui.chat_view import ChatView
    cv = ChatView()
    cv.add_message("user", "你好呀，在吗", ts=1)
    row = cv.start_ai_bubble()
    cv.append_chunk(row, "在的")
    cv.append_chunk(row, "～")
    cv.finalize_ai(row, "在的～")
    cv.add_system("已连接服务端")
    cv.add_message("assistant", "再见咯", ts=2)
    qapp.processEvents()                      # 触发布局/绘制，不崩即通过


def test_main_window_builds_and_dispatches(qapp, tmp_path, mock_ws):
    """构造主窗口（mock_ws 不真起 WS 线程）+ 直接驱动各收消息路径，验证不崩且能正常关闭"""
    from config import ClientConfig
    from ui.main_window import MainWindow
    cfg = ClientConfig(
        ws_url="ws://127.0.0.1:1/ws", rest_url="http://127.0.0.1:1",
        token="t", object_id="t", db_path=tmp_path / "chat.db", message_limit=50,
    )
    win = MainWindow(cfg)
    qapp.processEvents()
    # 直接驱动收消息分发（绕过真实 WS）：流式 / 错误 / 主动消息
    win._on_msg({"type": "ai_start", "payload": {}})
    win._on_msg({"type": "ai_chunk", "payload": {"delta": {"text": "嗨"}}})
    win._on_msg({"type": "ai_done", "payload": {"text": "嗨"}})
    win._on_msg({"type": "error", "payload": {"message": "测试错误"}})
    win._on_msg({"type": "proactive_msg", "payload": {"text": "在吗？"}})
    qapp.processEvents()
    win.close()                               # 触发 closeEvent：quit WS + store.close
    qapp.processEvents()

