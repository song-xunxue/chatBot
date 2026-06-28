"""
.star 加载器 + 适配器(M6)
StarLoader:扫描 .star 目录 → importlib 加载(触发 @filter/Star 注册副作用)→ 收集本地
registry 的 Star 类与 handler → 实例化 Star(注入 Context)→ 适配注册到 V2.0 EventBus/ToolRegistry。

适配映射(docs/04 §8.1):
  @command/@regex      → on_message_in(前缀/正则匹配,命中调 handler;返回文本→reply_text+STOP)
  @on_llm_request       → on_before_llm(handler 可改 system_prompt)
  @on_llm_response      → on_after_llm
  @after_message_sent   → on_message_out
  @llm_tool             → ToolRegistry 注册(M5 tool-loop 调用)

加载失败隔离(单 .star 异常不影响其他)。深度 API(群/@/Provider/Config)依赖的插件降级。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M6 新建 StarLoader:扫描加载 .star + Star 实例化 + handler 适配到 EventBus/ToolRegistry
"""
import importlib.util
import logging
import sys
from pathlib import Path

# 自举:把 star_compat/ 加入 sys.path,使 astrbot 兼容包可 import(.star 插件与加载器共用)
_COMPAT_DIR = Path(__file__).resolve().parent
if str(_COMPAT_DIR) not in sys.path:
    sys.path.insert(0, str(_COMPAT_DIR))

from astrbot._registry import (   # noqa: E402
    EventType, get_star_classes, get_star_handlers, clear_registry,
)
from astrbot.api.event import AstrMessageEvent   # noqa: E402
from astrbot.api.star import Context   # noqa: E402
from astrbot.api.provider import ProviderRequest, LLMResponse   # noqa: E402

from plugins.base import (   # noqa: E402
    ON_MESSAGE_IN, ON_BEFORE_LLM, ON_AFTER_LLM, ON_MESSAGE_OUT, HookResult,
)

logger = logging.getLogger(__name__)


class StarLoader:
    """.star 插件加载器:加载 + 适配注册到 V2.0 EventBus / ToolRegistry"""

    def __init__(self, bus, tool_registry, redis, settings):
        self._bus = bus
        self._tools = tool_registry
        self._redis = redis
        self._settings = settings
        self._stars: dict[str, object] = {}          # Star 名 → 实例
        self._cls_by_module: dict[str, str] = {}     # handler_module → Star 名(归属查找)
        self._registered: list[str] = []             # 已订阅 bus 的 plugin_name(unload 用)

    async def load_dir(self, star_dir) -> list[str]:
        """扫描 star_dir(*.py,跳过 _ 前缀)→ 加载 → 实例化 Star → 适配注册 handler。
        返回成功加载的模块名(无 .py 后缀)。"""
        clear_registry()                              # 加载前清(防 reload 重复)
        loaded: list[str] = []
        star_dir = Path(star_dir) if star_dir else None
        if not star_dir or not star_dir.is_dir():
            return loaded
        for py in sorted(star_dir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            try:
                self._import_module(py)
                loaded.append(py.stem)
            except Exception:
                logger.exception("load .star failed, isolated: %s", py)
        await self._instantiate_and_adapt()
        return loaded

    def _import_module(self, py_path: Path):
        """按文件路径 import .star 模块(触发 @filter/Star 注册副作用)"""
        mod_name = f"_mychat_star_{py_path.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, py_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法建立 spec: {py_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module

    async def _instantiate_and_adapt(self) -> None:
        """实例化所有 Star 子类(initialize)→ 适配注册各 handler"""
        # 1. 实例化 Star(initialize 注入 Context)
        for cls_md in get_star_classes():
            cls = cls_md.star_cls
            try:
                instance = cls(context=Context(redis=self._redis, settings=self._settings))
                await instance.initialize()
                self._stars[cls_md.name] = instance
                self._cls_by_module[cls_md.module] = cls_md.name
            except Exception:
                logger.exception("instantiate Star failed, isolated: %s", cls_md.name)
        # 2. 适配 handler
        for h_md in get_star_handlers():
            instance = self._stars.get(self._cls_by_module.get(h_md.handler_module, ""))
            if instance is None:
                logger.warning(".star handler %s 无归属 Star 实例,跳过", h_md.handler_name)
                continue
            try:
                self._adapt_handler(h_md, instance)
            except Exception:
                logger.exception("adapt handler failed: %s", h_md.handler_name)

    def _adapt_handler(self, h_md, instance) -> None:
        """按 event_type 适配注册到 V2.0 EventBus / ToolRegistry"""
        plugin_name = f"star:{h_md.handler_name}"
        et = h_md.event_type
        if et == EventType.AdapterMessageEvent:
            self._bus.subscribe(ON_MESSAGE_IN, plugin_name, 100,
                                self._make_message_gate(instance, h_md))
            self._registered.append(plugin_name)
        elif et == EventType.OnLLMRequestEvent:
            self._bus.subscribe(ON_BEFORE_LLM, plugin_name, 100,
                                self._make_llm_gate(instance, h_md.handler, "request"))
            self._registered.append(plugin_name)
        elif et == EventType.OnLLMResponseEvent:
            self._bus.subscribe(ON_AFTER_LLM, plugin_name, 100,
                                self._make_llm_gate(instance, h_md.handler, "response"))
            self._registered.append(plugin_name)
        elif et == EventType.OnAfterMessageSentEvent:
            self._bus.subscribe(ON_MESSAGE_OUT, plugin_name, 100,
                                self._make_simple_gate(instance, h_md.handler))
            self._registered.append(plugin_name)
        elif et == EventType.OnCallingFuncToolEvent:
            self._register_llm_tool(instance, h_md)

    # —— 钩子门控构造 ——

    def _make_message_gate(self, instance, h_md):
        """@command/@regex → on_message_in:前缀/正则匹配 → 调 handler → 结果设 reply_text"""
        async def gate(mctx):
            event = AstrMessageEvent(mctx)
            text = (mctx.user_text or "").strip()
            if h_md.filter_type == "command":
                if not text.startswith(h_md.filter_spec):
                    return HookResult.CONTINUE
            elif h_md.filter_type == "regex":
                if not h_md.filter_spec.search(text):
                    return HookResult.CONTINUE
            try:
                result = await h_md.handler(instance, event)
            except Exception:
                logger.exception(".star command/regex handler failed: %s", h_md.handler_name)
                return HookResult.CONTINUE
            # 结果:str/MessageEventResult → 设 reply_text + STOP(指令处理完跳过 LLM)
            if isinstance(result, str) and result:
                mctx.reply_text = result
                return HookResult.STOP
            if result is not None and getattr(result, "text", ""):
                mctx.reply_text = result.text
                return HookResult.STOP
            return HookResult.STOP if event.is_stopped() else HookResult.CONTINUE
        return gate

    def _make_llm_gate(self, instance, handler, kind: str):
        """@on_llm_request/@on_llm_response → on_before_llm/on_after_llm(handler 可改 prompt/resp)"""
        async def gate(mctx):
            event = AstrMessageEvent(mctx)
            try:
                if kind == "request":
                    req = ProviderRequest(system_prompt=mctx.system_prompt)
                    await handler(instance, event, req)
                    mctx.system_prompt = req.system_prompt
                else:
                    resp = LLMResponse(completion_text=mctx.reply_text)
                    await handler(instance, event, resp)
            except Exception:
                logger.exception(".star llm handler failed: %s", handler.__name__)
            return HookResult.STOP if event.is_stopped() else HookResult.CONTINUE
        return gate

    def _make_simple_gate(self, instance, handler):
        """@after_message_sent → on_message_out(透传 event)"""
        async def gate(mctx):
            event = AstrMessageEvent(mctx)
            try:
                await handler(instance, event)
            except Exception:
                logger.exception(".star message_out handler failed: %s", handler.__name__)
            return HookResult.CONTINUE
        return gate

    def _register_llm_tool(self, instance, h_md):
        """@llm_tool → ToolRegistry 注册(execute 调原 handler)。
        M6 简化:parameters 空 schema(不解析 docstring 参数,留后续);真参数工具需后续完善。"""
        from tools.base import Tool, ToolContext

        tool_name = str(h_md.filter_spec)
        handler = h_md.handler

        class _StarLLMTool(Tool):
            name = tool_name
            description = h_md.desc or tool_name
            parameters = {"type": "object", "properties": {}}   # M6 占位(参数解析留后续)

            async def execute(self, args, ctx: ToolContext):
                # 构造 event(V2.0 MessageContext 适配);handler 签名 (event, **params)
                from pipeline.context import MessageContext
                mctx = MessageContext(object_id=ctx.object_id)
                event = AstrMessageEvent(mctx)
                try:
                    result = await handler(instance, event, **(args or {}))
                except Exception as e:
                    return f"[.star llm_tool {tool_name} 执行失败: {e}]"
                if result is None:
                    return ""
                return result if isinstance(result, str) else getattr(result, "text", str(result))

        self._tools.register(_StarLLMTool())
        logger.info(".star llm_tool registered: %s", tool_name)

    # —— 卸载 ——

    async def unload_all(self) -> None:
        """卸载所有:terminate Star 实例 → 摘 EventBus 订阅 → 清 registry"""
        for name, inst in list(self._stars.items()):
            try:
                await inst.terminate()
            except Exception:
                logger.exception("Star terminate failed: %s", name)
        for plugin_name in self._registered:
            self._bus.unsubscribe_plugin(plugin_name)
        self._stars.clear()
        self._cls_by_module.clear()
        self._registered.clear()
        clear_registry()

    def list_loaded(self) -> list[str]:
        return sorted(self._stars.keys())
