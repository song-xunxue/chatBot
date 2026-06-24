"""
ws.py 的 ai_done payload 构造测试：文本 / 富内容 rich / 状态 state.mood。
_build_ai_done_payload 抽为模块级函数便于单测（客户端据此渲染图像/语音/心情）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 多模态：覆盖 ai_done payload 携带 rich + state.mood
"""
from types import SimpleNamespace

from api.ws import _build_ai_done_payload


def _ctx(reply="", rich=None, mood=None):
    pm = {}
    if mood:
        pm["mood"] = mood
    return SimpleNamespace(reply_text=reply, rich=rich or {}, plugin_meta=pm)


def test_payload_text_only():
    assert _build_ai_done_payload(_ctx(reply="你好")) == {"text": "你好"}


def test_payload_includes_rich():
    ctx = _ctx(reply="看图", rich={"image": [{"url": "http://x/a.png"}]})
    p = _build_ai_done_payload(ctx)
    assert p["text"] == "看图"
    assert p["rich"] == {"image": [{"url": "http://x/a.png"}]}


def test_payload_includes_mood_state():
    p = _build_ai_done_payload(_ctx(reply="嗨", mood="开心"))
    assert p["state"] == {"mood": "开心"}


def test_payload_omits_empty_rich_and_state():
    p = _build_ai_done_payload(_ctx(reply="x"))
    assert "rich" not in p
    assert "state" not in p
