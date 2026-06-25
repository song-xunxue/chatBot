"""
管道钩子集成测试：run_stream 在 on_message_in / on_before_llm / on_after_llm 触发插件钩子。
镜像 test_e2e_memory 的 provider mock 模式（patch stages.get_provider）；关闭记忆以聚焦钩子。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.1 覆盖 run_stream 三类钩子语义：丢弃(STOP)/跳过 LLM(STOP)/改写回复(CONTINUE)
"""
import pytest

from core.config import settings
from pipeline.context import MessageContext
from pipeline import runner, stages
from llm.base import Delta
from persona import store as persona_store
from plugins import init_plugins, shutdown_plugins


class _FakeProvider:
    """假 LLM：stream_chat 产固定 token；记录是否被调用"""
    name = "fake"

    def __init__(self):
        self.received = None
        self.called = False

    async def stream_chat(self, messages, model="", **opts):
        self.called = True
        self.received = messages
        for t in ["好", "的"]:
            yield Delta(text=t)


@pytest.fixture
def fake_provider(monkeypatch):
    fp = _FakeProvider()
    monkeypatch.setattr(stages, "get_provider", lambda name: fp)   # patch stages 内的 get_provider
    return fp


def _write_plugin(tmp_path, name, body_py, hook_name):
    """在 tmp_path/plugins/<name> 下写一个单钩子插件，返回插件根目录"""
    d = tmp_path / "plugins" / name
    d.mkdir(parents=True)
    (d / "plugin.yaml").write_text(
        f"name: {name}\nversion: 0.1.0\nentry: plugin.py\n"
        f"hooks:\n  - {{ name: {hook_name}, priority: 100 }}\n"
        f"default_enabled: false\n",
        encoding="utf-8",
    )
    (d / "plugin.py").write_text(body_py, encoding="utf-8")
    return tmp_path / "plugins"


async def _bootstrap(fake_redis, monkeypatch, plugin_dir):
    """把全局插件系统指向 plugin_dir 并初始化（设全局总线），返回管理器"""
    monkeypatch.setattr(settings, "plugin_dir", str(plugin_dir))
    return await init_plugins(fake_redis)


async def test_on_before_llm_stop_skips_llm(fake_redis, monkeypatch, tmp_path, fake_provider):
    """on_before_llm 返回 STOP：跳过 LLM，reply_text 由插件设置，provider 不被调用"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await persona_store.get_default_persona(fake_redis)
    py = (
        "from plugins.base import Plugin, HookResult\n\n"
        "class StopperPlugin(Plugin):\n"
        "    async def on_before_llm(self, ctx):\n"
        "        ctx.reply_text = '[plugin-reply]'\n"
        "        return HookResult.STOP\n")
    pdir = _write_plugin(tmp_path, "stopper", py, "on_before_llm")
    try:
        mgr = await _bootstrap(fake_redis, monkeypatch, pdir)
        await mgr.set_global_enabled("stopper", True)
        ctx = MessageContext(object_id="u", user_text="hi", provider_name="glm", created_ts=1)
        tokens = [t async for t in runner.run_stream(ctx)]
        assert tokens == []                       # 跳过 LLM → 无 token
        assert ctx.reply_text == "[plugin-reply]"
        assert fake_provider.called is False      # LLM 确实未被调用
    finally:
        await shutdown_plugins()


async def test_on_message_in_stop_drops(fake_redis, monkeypatch, tmp_path, fake_provider):
    """on_message_in 返回 STOP：整条消息丢弃，后续阶段不执行，provider 不被调用"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await persona_store.get_default_persona(fake_redis)
    py = (
        "from plugins.base import Plugin, HookResult\n\n"
        "class DropperPlugin(Plugin):\n"
        "    async def on_message_in(self, ctx):\n"
        "        return HookResult.STOP\n")
    pdir = _write_plugin(tmp_path, "dropper", py, "on_message_in")
    try:
        mgr = await _bootstrap(fake_redis, monkeypatch, pdir)
        await mgr.set_global_enabled("dropper", True)
        ctx = MessageContext(object_id="u", user_text="hi", provider_name="glm", created_ts=1)
        tokens = [t async for t in runner.run_stream(ctx)]
        assert tokens == []
        assert ctx.reply_text == ""
        assert fake_provider.called is False
    finally:
        await shutdown_plugins()


async def test_on_after_llm_appends_to_streamed_reply(fake_redis, monkeypatch, tmp_path, fake_provider):
    """正常流式 + on_after_llm 改写：token 正常产出，钩子在流结束后追加后缀"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await persona_store.get_default_persona(fake_redis)
    py = (
        "from plugins.base import Plugin, HookResult\n\n"
        "class AppendPlugin(Plugin):\n"
        "    async def on_after_llm(self, ctx):\n"
        "        ctx.reply_text = ctx.reply_text + '[T]'\n"
        "        return HookResult.CONTINUE\n")
    pdir = _write_plugin(tmp_path, "appender", py, "on_after_llm")
    try:
        mgr = await _bootstrap(fake_redis, monkeypatch, pdir)
        await mgr.set_global_enabled("appender", True)
        ctx = MessageContext(object_id="u", user_text="hi", provider_name="glm", created_ts=1)
        tokens = [t async for t in runner.run_stream(ctx)]
        assert tokens == ["好", "的"]              # 正常流式
        assert ctx.reply_text == "好的[T]"         # 钩子在流结束后追加
    finally:
        await shutdown_plugins()


async def test_no_plugin_system_backward_compat(fake_redis, monkeypatch, tmp_path, fake_provider):
    """插件系统未初始化（get_event_bus()==None）时 run_stream 退化为 M3 行为，正常流式回复"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await persona_store.get_default_persona(fake_redis)
    try:
        ctx = MessageContext(object_id="u", user_text="hi", provider_name="glm", created_ts=1)
        tokens = [t async for t in runner.run_stream(ctx)]
        assert tokens == ["好", "的"]
        assert ctx.reply_text == "好的"
    finally:
        await shutdown_plugins()


async def test_on_message_out_persists_to_history(fake_redis, monkeypatch, tmp_path, fake_provider):
    """on_message_out 对 reply_text 的改写会写入历史（stage_save 在其后执行）"""
    from storage import chat_store
    monkeypatch.setattr(settings, "memory_enabled", False)
    await persona_store.get_default_persona(fake_redis)
    py = (
        "from plugins.base import Plugin, HookResult\n\n"
        "class EnhancePlugin(Plugin):\n"
        "    async def on_message_out(self, ctx):\n"
        "        ctx.reply_text = ctx.reply_text + '[OUT]'\n"
        "        return HookResult.CONTINUE\n")
    pdir = _write_plugin(tmp_path, "enhancer", py, "on_message_out")
    try:
        mgr = await _bootstrap(fake_redis, monkeypatch, pdir)
        await mgr.set_global_enabled("enhancer", True)
        ctx = MessageContext(object_id="u", user_text="hi", provider_name="glm", created_ts=1)
        async for _ in runner.run_stream(ctx):
            pass
        assert ctx.reply_text == "好的[OUT]"
        hist = await chat_store.get_history(fake_redis, "u", limit=5)
        assistant_msgs = [m for m in hist if m.role == "assistant"]
        assert assistant_msgs and assistant_msgs[-1].content == "好的[OUT]"
    finally:
        await shutdown_plugins()


async def test_on_after_llm_stop_skips_message_out(fake_redis, monkeypatch, tmp_path, fake_provider):
    """on_after_llm 返回 STOP → 跳过 on_message_out（不进入回复增强）"""
    monkeypatch.setattr(settings, "memory_enabled", False)
    await persona_store.get_default_persona(fake_redis)
    d = tmp_path / "plugins"
    (d / "after_stop").mkdir(parents=True)
    (d / "after_stop" / "plugin.yaml").write_text(
        "name: after_stop\nversion: 0.1.0\nentry: plugin.py\n"
        "hooks:\n  - { name: on_after_llm, priority: 50 }\ndefault_enabled: false\n", encoding="utf-8")
    (d / "after_stop" / "plugin.py").write_text(
        "from plugins.base import Plugin, HookResult\n"
        "class AfterStopPlugin(Plugin):\n"
        "    async def on_after_llm(self, ctx):\n"
        "        return HookResult.STOP\n", encoding="utf-8")
    (d / "out_track").mkdir(parents=True)
    (d / "out_track" / "plugin.yaml").write_text(
        "name: out_track\nversion: 0.1.0\nentry: plugin.py\n"
        "hooks:\n  - { name: on_message_out, priority: 50 }\ndefault_enabled: false\n", encoding="utf-8")
    (d / "out_track" / "plugin.py").write_text(
        "from plugins.base import Plugin, HookResult\n"
        "class OutTrackPlugin(Plugin):\n"
        "    async def on_message_out(self, ctx):\n"
        "        ctx.plugin_meta['out_called'] = True\n"
        "        return HookResult.CONTINUE\n", encoding="utf-8")
    try:
        mgr = await _bootstrap(fake_redis, monkeypatch, d)
        await mgr.set_global_enabled("after_stop", True)
        await mgr.set_global_enabled("out_track", True)
        ctx = MessageContext(object_id="u", user_text="hi", provider_name="glm", created_ts=1)
        async for _ in runner.run_stream(ctx):
            pass
        assert ctx.plugin_meta.get("out_called") is not True   # on_message_out 被 STOP 跳过
    finally:
        await shutdown_plugins()
