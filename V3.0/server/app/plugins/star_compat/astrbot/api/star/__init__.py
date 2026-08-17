"""astrbot.api.star 兼容(V2.0 子集):Star 基类 + Context + StarTools + register。

Star:所有 .star 插件基类,__init_subclass__ 自动注册到本地 registry。
Context:V2.0 能力子集(redis/settings),StarLoader 实例化时注入。

作者: 李文煜
日期: 2026-06-28
"""


class Star:
    """所有 .star 插件的父类(对应 AstrBot Star)。
    __init_subclass__ 自动把子类注册到本地 registry,StarLoader 收集。"""
    author: str = ""
    name: str = ""

    def __init__(self, context=None, config=None) -> None:
        self.context = context
        self.config = config or {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from astrbot._registry import register_star_class
        register_star_class(cls)

    async def initialize(self) -> None:
        """插件激活时调用(对应 AstrBot initialize)"""

    async def terminate(self) -> None:
        """插件禁用/重载时调用(对应 AstrBot terminate)"""


class Context:
    """V2.0 能力子集(对应 AstrBotContext,仅暴露私聊场景能提供的):
    redis / settings + 委托 write_memory / get_persona_text。
    深度 API(get_provider_by_id / get_config / 平台等)不提供,依赖其的插件需自行降级。"""

    def __init__(self, redis=None, settings=None, object_id: str = ""):
        self._redis = redis
        self._settings = settings
        self._object_id = object_id

    @property
    def redis(self):
        return self._redis

    @property
    def settings(self):
        return self._settings

    @property
    def object_id(self) -> str:
        return self._object_id

    async def write_memory(self, content: str, category: str = "fact",
                           importance: float = 0.5) -> str:
        """委托 V2.0 tools.write_memory 工具逻辑:写长期记忆"""
        from tools.builtin import WriteMemoryTool
        from tools.base import ToolContext
        return await WriteMemoryTool().execute(
            {"content": content, "category": category, "importance": importance},
            ToolContext(redis=self._redis, object_id=self._object_id))

    async def get_persona_text(self) -> str:
        """委托 V2.0 tools.get_persona:查当前对象人设摘要"""
        from tools.builtin import GetPersonaTool
        from tools.base import ToolContext
        return await GetPersonaTool().execute(
            {}, ToolContext(redis=self._redis, object_id=self._object_id))


# StarTools 占位(AstrBot 提供,本兼容层暂空)
StarTools = type("StarTools", (), {})


def register(*args, **kwargs):
    """@register_star 类装饰器兼容(Star 子类已自动注册,此处仅透传)"""
    def deco(cls):
        return cls
    # 兼容直接 @register 用法(无括号)
    if args and isinstance(args[0], type):
        return args[0]
    return deco
