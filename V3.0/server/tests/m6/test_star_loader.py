"""
StarLoader 单测:加载 mock .star 插件 → Star 实例化(initialize)→ @command/@regex 适配
ON_MESSAGE_IN(匹配触发+STOP)、@on_llm_request 适配 ON_BEFORE_LLM(改 prompt)、
@llm_tool 注册 ToolRegistry(execute 调原 handler)。加载失败隔离。

作者: 李文煜
日期: 2026-06-28
"""
from pipeline.context import MessageContext
from plugins.base import ON_MESSAGE_IN, ON_BEFORE_LLM, HookResult
from tools.base import ToolContext
from plugins.star_compat.star_loader import StarLoader

# mock .star 插件(用 V2.0 兼容包 API)
_MOCK_STAR = '''
from astrbot.api.star import Star
from astrbot.api.event.filter import command, regex, on_llm_request, llm_tool


class MockStar(Star):
    async def initialize(self):
        self.init_called = True

    @command("hello")
    async def hello(self, event):
        return "你好呀"

    @regex(r"天气")
    async def weather(self, event):
        return "天气查询"

    @on_llm_request()
    async def on_req(self, event, req):
        req.system_prompt += "[star 注入]"

    @llm_tool("star_tool")
    async def star_tool(self, event, x):
        return f"star:{x}"
'''


async def test_star_loader_loads_and_adapts(fake_redis, bus, tool_registry, tmp_path):
    """加载 mock .star → Star 实例化 + handler 适配到 EventBus/ToolRegistry"""
    star_file = tmp_path / "mock_star.py"
    star_file.write_text(_MOCK_STAR, encoding="utf-8")
    loader = StarLoader(bus, tool_registry, fake_redis, None)
    loaded = await loader.load_dir(tmp_path)
    assert loaded == ["mock_star"]
    assert "MockStar" in loader._stars
    assert getattr(loader._stars["MockStar"], "init_called", False)   # initialize 被调

    # @command "hello" → ON_MESSAGE_IN 前缀匹配 → reply_text + STOP
    ctx = MessageContext(object_id="u1", user_text="hello")
    assert await bus.fire(ON_MESSAGE_IN, ctx) == HookResult.STOP
    assert ctx.reply_text == "你好呀"

    # @regex "天气" → ON_MESSAGE_IN 正则匹配
    ctx2 = MessageContext(object_id="u1", user_text="今天天气如何")
    await bus.fire(ON_MESSAGE_IN, ctx2)
    assert ctx2.reply_text == "天气查询"

    # 不匹配 → CONTINUE,reply_text 不变
    ctx3 = MessageContext(object_id="u1", user_text="别的")
    assert await bus.fire(ON_MESSAGE_IN, ctx3) == HookResult.CONTINUE
    assert ctx3.reply_text == ""

    # @on_llm_request → ON_BEFORE_LLM 改 system_prompt
    ctx4 = MessageContext(object_id="u1", user_text="x", system_prompt="base")
    await bus.fire(ON_BEFORE_LLM, ctx4)
    assert "[star 注入]" in ctx4.system_prompt

    # @llm_tool → ToolRegistry 注册,execute 调原 handler
    tool = tool_registry.get("star_tool")
    assert tool is not None
    out = await tool.execute({"x": "v"}, ToolContext(object_id="u1"))
    assert out == "star:v"


async def test_star_loader_empty_dir(fake_redis, bus, tool_registry, tmp_path):
    """空目录 → 加载 0 个,不报错"""
    loader = StarLoader(bus, tool_registry, fake_redis, None)
    assert await loader.load_dir(tmp_path) == []


async def test_star_loader_bad_file_isolated(fake_redis, bus, tool_registry, tmp_path):
    """单个 .star 语法错误 → 隔离不影响(返回空,不抛)"""
    (tmp_path / "bad.py").write_text("this is not valid python !!!", encoding="utf-8")
    loader = StarLoader(bus, tool_registry, fake_redis, None)
    loaded = await loader.load_dir(tmp_path)   # 不抛
    assert loaded == []


async def test_star_loader_unload(fake_redis, bus, tool_registry, tmp_path):
    """unload 后摘订阅 + 清实例"""
    star_file = tmp_path / "mock_star.py"
    star_file.write_text(_MOCK_STAR, encoding="utf-8")
    loader = StarLoader(bus, tool_registry, fake_redis, None)
    await loader.load_dir(tmp_path)
    assert bus.subscribers(ON_MESSAGE_IN) != []
    await loader.unload_all()
    assert bus.subscribers(ON_MESSAGE_IN) == []
    assert loader.list_loaded() == []
