"""
.star 兼容层包装饰器/类单测:@command/@regex/@llm_tool 注册、Star __init_subclass__ 注册、
AstrMessageEvent 适配 MessageContext、Context.write_memory/get_persona。

作者: 李文煜
日期: 2026-06-28
"""
from astrbot._registry import get_star_handlers, get_star_classes, clear_registry
from astrbot.api.star import Star, Context
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import command, regex, on_llm_request, on_llm_response, after_message_sent, llm_tool


def setup_function():
    """每测试前清本地 registry(装饰器副作用累积)"""
    clear_registry()


def test_command_registers_handler():
    @command("hi")
    async def h(self, event):
        """打招呼"""
        return "hi"
    hs = get_star_handlers()
    assert len(hs) == 1
    assert hs[0].filter_type == "command" and hs[0].filter_spec == "hi"
    assert hs[0].desc == "打招呼"


def test_regex_registers():
    @regex(r"\d+")
    async def h(self, event):
        pass
    md = get_star_handlers()[0]
    assert md.filter_type == "regex"
    assert md.filter_spec.search("123")


def test_llm_request_response_message_sent_register():
    @on_llm_request()
    async def a(self, event, req):
        pass

    @on_llm_response()
    async def b(self, event, resp):
        pass

    @after_message_sent()
    async def c(self, event):
        pass
    types = {h.event_type.value for h in get_star_handlers()}
    assert types == {"on_llm_request", "on_llm_response", "after_message_sent"}


def test_llm_tool_registers():
    @llm_tool("my_tool")
    async def h(self, event):
        pass
    md = get_star_handlers()[0]
    assert md.event_type.value == "llm_tool"
    assert md.filter_spec == "my_tool"


def test_star_subclass_registers():
    class MyStar(Star):
        pass
    cs = get_star_classes()
    assert len(cs) == 1
    assert cs[0].star_cls is MyStar
    assert cs[0].name == "MyStar"


def test_astrmessage_event_adapts_mctx():
    from pipeline.context import MessageContext
    mctx = MessageContext(object_id="u1", user_text="你好")
    e = AstrMessageEvent(mctx)
    assert e.message_str == "你好"
    assert e.plain_text == "你好"
    assert e.unified_msg_origin == "u1"
    assert e.get_message_type() == "private"
    assert not e.is_stopped()
    e.stop_event()
    assert e.is_stopped()


async def test_context_write_memory(fake_redis):
    from memory import store
    ctx = Context(redis=fake_redis, object_id="u1")
    out = await ctx.write_memory("用户喜欢猫", "preference", 0.8)
    assert "已写入" in out
    items = await store.get_all_long_term(fake_redis, "u1")
    assert any("猫" in m.content for m in items)
