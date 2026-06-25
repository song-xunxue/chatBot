"""
sticker_gen 插件测试：生成表情包入 ctx.rich.sticker。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 覆盖 sticker_gen：生成/空跳过
"""
from plugins.base import ON_AFTER_LLM


def _ctx(reply="", oid="o1"):
    return type("C", (), {
        "object_id": oid, "user_text": "", "reply_text": reply,
        "rich": {}, "plugin_meta": {},
    })()


async def test_generates_sticker(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("sticker_gen", True)
    ctx = _ctx(reply="好开心")
    await real_manager._bus.fire(ON_AFTER_LLM, ctx)
    assert len(ctx.rich.get("sticker", [])) == 1
    assert ctx.rich["sticker"][0]["url"].startswith("stub://img/")


async def test_skip_when_empty(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("sticker_gen", True)
    ctx = _ctx(reply="")
    await real_manager._bus.fire(ON_AFTER_LLM, ctx)
    assert len(ctx.rich.get("sticker", [])) == 0
