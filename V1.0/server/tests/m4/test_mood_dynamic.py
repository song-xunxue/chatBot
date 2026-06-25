"""
mood_dynamic 插件测试：正向/负向情感更新心情、注入 prompt、on_tick 衰减。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 覆盖 mood_dynamic：情感更新/注入/衰减
"""
from plugins.base import ON_BEFORE_LLM, ON_AFTER_LLM, ON_TICK


def _ctx(reply="", oid="o1", sysprompt="你是小聊"):
    return type("C", (), {
        "object_id": oid, "user_text": "", "reply_text": reply,
        "system_prompt": sysprompt, "plugin_meta": {},
    })()


async def _mood(mgr, oid):
    v = await mgr._redis.get(f"mychat:mood:{oid}")
    return float(v) if v is not None else 0.5


async def test_positive_reply_raises_mood(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("mood_dynamic", True)
    await real_manager._bus.fire(ON_AFTER_LLM, _ctx(reply="今天好开心呀，哈哈"))
    assert await _mood(real_manager, "o1") > 0.5


async def test_negative_reply_lowers_mood(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("mood_dynamic", True)
    await real_manager._bus.fire(ON_AFTER_LLM, _ctx(reply="好累，有点难过"))
    assert await _mood(real_manager, "o1") < 0.5


async def test_mood_injected_into_prompt(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("mood_dynamic", True)
    c = _ctx(sysprompt="你是小聊")
    await real_manager._bus.fire(ON_BEFORE_LLM, c)
    assert "心情" in c.system_prompt


async def test_tick_decays_mood(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("mood_dynamic", True)
    await real_manager._redis.set("mychat:mood:o1", "0.9")
    await real_manager._bus.fire(ON_TICK, _ctx())
    assert await _mood(real_manager, "o1") < 0.9      # 向中性衰减
