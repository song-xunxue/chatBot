"""
StarLoader.reload_file 增量热重载单测(M7)。
验证:reload 单文件不误卸其他 .star(避开 clear_registry 全清)、reload 后文件改动生效、文件不存在返回 False。

作者: 李文煜
日期: 2026-06-30
"""
from pipeline.context import MessageContext
from plugins.base import ON_MESSAGE_IN, HookResult
from plugins.star_compat.star_loader import StarLoader

# 两个独立 .star 插件(各自 @command)
_STAR_A = '''
from astrbot.api.star import Star
from astrbot.api.event.filter import command


class StarA(Star):
    async def initialize(self):
        pass

    @command("aaa")
    async def cmd_a(self, event):
        return "A响应"
'''

_STAR_B = '''
from astrbot.api.star import Star
from astrbot.api.event.filter import command


class StarB(Star):
    async def initialize(self):
        pass

    @command("bbb")
    async def cmd_b(self, event):
        return "B响应"
'''


async def test_reload_file_keeps_other_star(fake_redis, bus, tool_registry, tmp_path):
    """reload A 后 B 仍在 bus(增量热重载,不全清)"""
    (tmp_path / "star_a.py").write_text(_STAR_A, encoding="utf-8")
    (tmp_path / "star_b.py").write_text(_STAR_B, encoding="utf-8")
    loader = StarLoader(bus, tool_registry, fake_redis, None)
    await loader.load_dir(tmp_path)
    assert "StarA" in loader._stars
    assert "StarB" in loader._stars

    # reload A
    assert await loader.reload_file("star_a") is True

    # A 仍可响应(reload 后重新适配)
    ctx_a = MessageContext(object_id="u1", user_text="aaa")
    assert await bus.fire(ON_MESSAGE_IN, ctx_a) == HookResult.STOP
    assert ctx_a.reply_text == "A响应"
    # B 未被误卸,仍可响应
    ctx_b = MessageContext(object_id="u1", user_text="bbb")
    await bus.fire(ON_MESSAGE_IN, ctx_b)
    assert ctx_b.reply_text == "B响应"
    assert "StarA" in loader._stars
    assert "StarB" in loader._stars


async def test_reload_file_picks_up_changes(fake_redis, bus, tool_registry, tmp_path):
    """reload 后文件改动生效(改回复文本)"""
    f = tmp_path / "star_a.py"
    f.write_text(_STAR_A, encoding="utf-8")
    loader = StarLoader(bus, tool_registry, fake_redis, None)
    await loader.load_dir(tmp_path)
    ctx = MessageContext(object_id="u1", user_text="aaa")
    await bus.fire(ON_MESSAGE_IN, ctx)
    assert ctx.reply_text == "A响应"

    # 改文件:替换回复文本
    f.write_text(_STAR_A.replace("A响应", "A新响应"), encoding="utf-8")
    assert await loader.reload_file("star_a") is True
    ctx2 = MessageContext(object_id="u1", user_text="aaa")
    await bus.fire(ON_MESSAGE_IN, ctx2)
    assert ctx2.reply_text == "A新响应"


async def test_reload_file_not_found(fake_redis, bus, tool_registry, tmp_path):
    """reload 不存在的文件 → False(隔离,不抛)"""
    loader = StarLoader(bus, tool_registry, fake_redis, None)
    await loader.load_dir(tmp_path)
    assert await loader.reload_file("no_such") is False


async def test_reload_no_star_dir(fake_redis, bus, tool_registry):
    """未 load_dir(_star_dir=None)→ reload 返回 False"""
    loader = StarLoader(bus, tool_registry, fake_redis, None)
    assert await loader.reload_file("any") is False
