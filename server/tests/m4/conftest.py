"""
M4 插件测试公共夹具
复用顶层 conftest 的 fake_redis（fakeredis 注入）；本文件提供临时插件目录、EventBus、PluginManager 夹具。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.1/M4.2 新增插件测试夹具（临时插件目录 echo + 跳过项 _skipme/noyaml、bus、manager）
"""
from pathlib import Path

import pytest

from plugins.event import EventBus
from plugins.manager import PluginManager


@pytest.fixture
def plugin_dir(tmp_path) -> Path:
    """构造临时插件目录：echo（可加载）+ _skipme（_ 前缀应跳过）+ noyaml（无 plugin.yaml 应跳过）"""
    d = tmp_path / "plugins"
    d.mkdir()
    # echo 插件：on_after_llm 追加 tag（读 config_schema 默认值 / 按对象覆盖）
    ep = d / "echo"
    ep.mkdir()
    (ep / "plugin.yaml").write_text(
        "name: echo\nversion: 0.1.0\nauthor: tester\n"
        "description: echo test plugin\nentry: plugin.py\n"
        "hooks:\n  - { name: on_after_llm, priority: 50 }\n"
        "default_enabled: false\n"
        "config_schema:\n  tag: { type: string, default: '[E]' }\n",
        encoding="utf-8",
    )
    (ep / "plugin.py").write_text(
        "from plugins.base import Plugin, HookResult\n\n\n"
        "class EchoPlugin(Plugin):\n"
        "    async def on_after_llm(self, ctx):\n"
        "        params = await self.get_params(ctx.object_id)\n"
        "        if ctx.reply_text:\n"
        "            ctx.reply_text = ctx.reply_text + params.get('tag', '[E]')\n"
        "        return HookResult.CONTINUE\n",
        encoding="utf-8",
    )
    # _skipme：_ 前缀目录，discover 应跳过
    sk = d / "_skipme"
    sk.mkdir()
    (sk / "plugin.yaml").write_text("name: skipme\nentry: plugin.py\n", encoding="utf-8")
    # noyaml：无 plugin.yaml 的目录，discover 应跳过
    (d / "noyaml").mkdir()
    return d


@pytest.fixture
def bus() -> EventBus:
    """空事件总线"""
    return EventBus()


@pytest.fixture
def manager(fake_redis, bus, plugin_dir) -> PluginManager:
    """PluginManager（绑定 fakeredis + 临时插件目录，尚未 load_all）"""
    return PluginManager(fake_redis, bus, plugin_dir)


@pytest.fixture
def real_manager(fake_redis, bus) -> PluginManager:
    """指向真实 server/app/plugins 目录的 PluginManager（绑定 fakeredis），用于加载 hello/各 M4.3/M4.4 插件"""
    from core.config import PROJECT_ROOT
    d = PROJECT_ROOT / "server" / "app" / "plugins"
    return PluginManager(fake_redis, bus, d)
