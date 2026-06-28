"""V2.0 .star 兼容层本地注册表(模拟 AstrBot star_registry / star_handlers)。
@filter 装饰器副作用注册到此;StarLoader 收集后适配到 V2.0 EventBus / ToolRegistry。

作者: 李文煜
日期: 2026-06-28
"""
from dataclasses import dataclass
from enum import Enum


class EventType(str, Enum):
    """.star handler 事件类型(子集)→ V2.0 钩子映射见 star_loader.adapter"""
    AdapterMessageEvent = "adapter_message"      # @command/@regex → on_message_in
    OnLLMRequestEvent = "on_llm_request"         # → on_before_llm
    OnLLMResponseEvent = "on_llm_response"       # → on_after_llm
    OnAfterMessageSentEvent = "after_message_sent"  # → on_message_out
    OnCallingFuncToolEvent = "llm_tool"          # → ToolRegistry


@dataclass
class StarHandlerMetadata:
    """单个 @filter handler 元数据"""
    event_type: EventType
    handler: object          # async (self, event, ...) → result
    handler_name: str
    handler_module: str
    filter_type: str = ""    # command / regex / llm_tool / ""
    filter_spec: object = None   # command 名 / regex pattern / llm_tool 名 / None
    desc: str = ""


@dataclass
class StarClassMetadata:
    """Star 子类元数据(__init_subclass__ 自动注册)"""
    star_cls: type
    module: str
    name: str = ""


# 本地 registry(StarLoader 收集)
_star_classes: list[StarClassMetadata] = []
_star_handlers: list[StarHandlerMetadata] = []


def register_star_class(cls) -> None:
    """Star.__init_subclass__ 调用:注册子类(同模块去重)"""
    existing = next((s for s in _star_classes if s.module == cls.__module__), None)
    if existing:
        existing.star_cls = cls
        existing.name = cls.__name__
    else:
        _star_classes.append(StarClassMetadata(star_cls=cls, module=cls.__module__, name=cls.__name__))


def register_handler(handler, event_type: EventType, *,
                     filter_type: str = "", filter_spec=None, desc: str = "") -> StarHandlerMetadata:
    """@filter 装饰器调用:注册 handler 元数据"""
    md = StarHandlerMetadata(
        event_type=event_type, handler=handler,
        handler_name=getattr(handler, "__name__", ""),
        handler_module=getattr(handler, "__module__", ""),
        filter_type=filter_type, filter_spec=filter_spec, desc=desc,
    )
    _star_handlers.append(md)
    return md


def get_star_classes() -> list[StarClassMetadata]:
    return list(_star_classes)


def get_star_handlers() -> list[StarHandlerMetadata]:
    return list(_star_handlers)


def clear_registry() -> None:
    """清空(测试用 / reload)"""
    _star_classes.clear()
    _star_handlers.clear()
