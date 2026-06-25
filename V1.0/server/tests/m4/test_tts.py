"""
tts 插件测试：合成音频入 ctx.rich.audio、过长跳过。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 覆盖 tts：合成/超长跳过
"""
from plugins.base import ON_AFTER_LLM


def _ctx(reply="", oid="o1"):
    return type("C", (), {
        "object_id": oid, "user_text": "", "reply_text": reply,
        "rich": {}, "plugin_meta": {},
    })()


async def test_synthesizes_audio(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("tts", True)
    ctx = _ctx(reply="你好呀")
    await real_manager._bus.fire(ON_AFTER_LLM, ctx)
    assert len(ctx.rich.get("audio", [])) == 1
    assert ctx.rich["audio"][0]["url"].startswith("stub://tts/")
    assert ctx.rich["audio"][0]["voice"] == "female-soft"


async def test_skip_when_too_long(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("tts", True)
    await real_manager.set_object_config("tts", "o1", True, {"max_chars": 5})
    ctx = _ctx(reply="一二三四五六七八九十")
    await real_manager._bus.fire(ON_AFTER_LLM, ctx)
    assert len(ctx.rich.get("audio", [])) == 0     # 超 max_chars 跳过
