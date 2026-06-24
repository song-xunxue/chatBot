"""
PluginManager 单测：发现（跳过 _/无yaml）、加载注册、默认关闭、全局+按对象开关、
参数合并、reload 不重复订阅、卸载移除订阅、门控（未启用不触发）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.1 覆盖 PluginManager 核心：discover/load/enable/config/reload/unload/gate
"""
from plugins.base import ON_AFTER_LLM


async def test_discover_skips_underscore_and_noyaml(manager):
    found = {m.name for m in manager.discover()}
    assert "echo" in found
    assert "skipme" not in found       # _ 前缀跳过
    assert "noyaml" not in found       # 无 plugin.yaml 跳过


async def test_load_registers_hook(manager, bus):
    loaded = await manager.load_all()
    assert loaded == ["echo"]
    subs = bus.subscribers(ON_AFTER_LLM)
    assert [s.plugin_name for s in subs] == ["echo"]


async def test_default_disabled(manager):
    await manager.load_all()
    # manifest default_enabled=false → 未显式全局开关时 is_enabled_for=False
    assert await manager.is_enabled_for("echo", "o1") is False


async def test_global_enable_then_per_object_disable(manager):
    await manager.load_all()
    await manager.set_global_enabled("echo", True)
    assert await manager.is_enabled_for("echo", "o1") is True       # 全局开 + 对象未设 → 启用
    await manager.set_object_config("echo", "o1", enabled=False, params=None)
    assert await manager.is_enabled_for("echo", "o1") is False      # 按对象关闭覆盖


async def test_params_merge_default_and_override(manager):
    await manager.load_all()
    assert await manager.get_params("echo", "o1") == {"tag": "[E]"}   # config_schema 默认值
    await manager.set_object_config("echo", "o1", None, {"tag": "[X]"})
    assert await manager.get_params("echo", "o1") == {"tag": "[X]"}   # 按对象覆盖


async def test_reload_no_duplicate_subscription(manager, bus):
    await manager.load_all()
    assert "echo" in manager.list_loaded()
    await manager.reload("echo")
    assert "echo" in manager.list_loaded()
    assert len(bus.subscribers(ON_AFTER_LLM)) == 1                  # reload 后不重复


async def test_unload_removes_subscription(manager, bus):
    await manager.load_all()
    assert len(bus.subscribers(ON_AFTER_LLM)) == 1
    assert await manager.unload("echo") is True
    assert len(bus.subscribers(ON_AFTER_LLM)) == 0
    assert "echo" not in manager.list_loaded()
    assert await manager.unload("echo") is False                    # 再次卸载返回 False


async def test_gate_skips_when_disabled_runs_when_enabled(manager, bus):
    """门控：未启用时钩子回调不执行；全局启用后才执行"""
    await manager.load_all()
    ctx = type("C", (), {"object_id": "o1", "reply_text": "hi"})()
    await bus.fire(ON_AFTER_LLM, ctx)
    assert ctx.reply_text == "hi"           # echo 未启用 → 不追加
    await manager.set_global_enabled("echo", True)
    await bus.fire(ON_AFTER_LLM, ctx)
    assert ctx.reply_text == "hi[E]"        # 启用 → 追加 tag


async def test_load_failure_rolls_back_no_leak(manager):
    """on_load 抛错的插件不残留 _loaded / sys.modules（回滚）"""
    import sys
    bad = manager._dir / "badplugin"
    bad.mkdir()
    (bad / "plugin.yaml").write_text(
        "name: badplugin\nversion: 0.1.0\nentry: plugin.py\n"
        "hooks:\n  - { name: on_after_llm, priority: 100 }\ndefault_enabled: false\n", encoding="utf-8")
    (bad / "plugin.py").write_text(
        "from plugins.base import Plugin, HookResult\n"
        "class BadPlugin(Plugin):\n"
        "    async def on_load(self):\n"
        "        raise RuntimeError('boom')\n", encoding="utf-8")
    loaded = await manager.load_all()
    assert "echo" in loaded
    assert "badplugin" not in loaded
    assert "badplugin" not in manager.list_loaded()
    assert "_mychat_plugin_badplugin" not in sys.modules


async def test_alive_gate_skips_unloaded_instance(manager, bus):
    """gate 校验 _alive：把已加载实例标记为不存活后，钩子不再执行"""
    await manager.load_all()
    await manager.set_global_enabled("echo", True)
    inst = manager.get_instance("echo")
    ctx = type("C", (), {"object_id": "o1", "reply_text": "hi"})()
    await bus.fire(ON_AFTER_LLM, ctx)
    assert ctx.reply_text == "hi[E]"        # 存活时执行
    inst._alive = False                      # 模拟卸载/不存活
    ctx2 = type("C", (), {"object_id": "o1", "reply_text": "hi"})()
    await bus.fire(ON_AFTER_LLM, ctx2)
    assert ctx2.reply_text == "hi"           # 不存活 → gate 跳过
