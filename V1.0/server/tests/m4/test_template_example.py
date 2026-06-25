"""
真实插件目录加载测试：hello 示例可加载、_template 被跳过、hello 钩子端到端生效。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.2 验证真实 plugins/ 目录（hello/_template）发现与加载
"""
import pytest

from core.config import PROJECT_ROOT
from plugins.event import EventBus
from plugins.manager import PluginManager
from plugins.base import ON_AFTER_LLM


@pytest.fixture
def real_manager(fake_redis):
    """指向真实 server/app/plugins 目录的 PluginManager（绑定 fakeredis）"""
    bus = EventBus()
    d = PROJECT_ROOT / "server" / "app" / "plugins"
    return PluginManager(fake_redis, bus, d)


async def test_hello_loaded_template_skipped(real_manager):
    loaded = await real_manager.load_all()
    assert "hello" in loaded
    assert "my-template-plugin" not in loaded     # _template（_ 前缀）被跳过


async def test_hello_on_after_llm(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("hello", True)
    ctx = type("C", (), {"object_id": "o1", "reply_text": "hi"})()
    await real_manager._bus.fire(ON_AFTER_LLM, ctx)   # 白盒：取管理器内部总线触发
    assert ctx.reply_text == "hi [hello]"             # hello 追加默认后缀


async def test_hello_params_override(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("hello", True)
    await real_manager.set_object_config("hello", "o1", True, {"suffix": "[YO]"})
    ctx = type("C", (), {"object_id": "o1", "reply_text": "hi"})()
    await real_manager._bus.fire(ON_AFTER_LLM, ctx)
    assert ctx.reply_text == "hi [YO]"                # 按对象参数覆盖生效
