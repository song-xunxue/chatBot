"""
time_aware 插件测试：注入时间上下文、缓存时辰标签。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 覆盖 time_aware：注入/缓存
"""
from plugins.base import ON_BEFORE_LLM, ON_TICK


def _ctx(oid="o1", sysprompt="你是小聊"):
    return type("C", (), {
        "object_id": oid, "user_text": "", "reply_text": "",
        "system_prompt": sysprompt, "plugin_meta": {},
    })()


async def test_time_injected_into_prompt(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("time_aware", True)
    c = _ctx()
    await real_manager._bus.fire(ON_BEFORE_LLM, c)
    assert "[当前时间：" in c.system_prompt
    assert "季" in c.system_prompt        # 含季节标签


async def test_tick_caches_time_label(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("time_aware", True)
    await real_manager._bus.fire(ON_TICK, _ctx())
    label = await real_manager._redis.get("mychat:timelabel:o1")
    assert label in {"清晨", "上午", "中午", "下午", "晚上", "深夜"}
