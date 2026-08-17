"""astrbot.api.event.filter 兼容(V2.0 子集)
@command/@regex/@on_llm_request/@on_llm_response/@after_message_sent/@llm_tool 装饰器。
装饰器副作用:把 handler 元数据注册到 astrbot._registry(StarLoader 收集),返回原函数不包装。

作者: 李文煜
日期: 2026-06-28
"""
import re

from astrbot._registry import EventType, register_handler


def command(command_name, **kwargs):
    """@command('name') → on_message_in(前缀匹配 command_name)"""
    def deco(fn):
        register_handler(fn, EventType.AdapterMessageEvent, filter_type="command",
                         filter_spec=command_name, desc=(fn.__doc__ or "").strip())
        return fn
    return deco


def regex(pattern, **kwargs):
    """@regex('pattern') → on_message_in(re.search 匹配)"""
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern

    def deco(fn):
        register_handler(fn, EventType.AdapterMessageEvent, filter_type="regex",
                         filter_spec=compiled, desc=(fn.__doc__ or "").strip())
        return fn
    return deco


def on_llm_request(**kwargs):
    """@on_llm_request → on_before_llm(handler 接收 event)"""
    def deco(fn):
        register_handler(fn, EventType.OnLLMRequestEvent, desc=(fn.__doc__ or "").strip())
        return fn
    return deco


def on_llm_response(**kwargs):
    """@on_llm_response → on_after_llm(handler 接收 event)"""
    def deco(fn):
        register_handler(fn, EventType.OnLLMResponseEvent, desc=(fn.__doc__ or "").strip())
        return fn
    return deco


def after_message_sent(**kwargs):
    """@after_message_sent → on_message_out(handler 接收 event)"""
    def deco(fn):
        register_handler(fn, EventType.OnAfterMessageSentEvent, desc=(fn.__doc__ or "").strip())
        return fn
    return deco


def llm_tool(name=None, **kwargs):
    """@llm_tool('name') → ToolRegistry 注册(M5 tool-loop 调用)"""
    def deco(fn):
        register_handler(fn, EventType.OnCallingFuncToolEvent, filter_type="llm_tool",
                         filter_spec=name or getattr(fn, "__name__", ""),
                         desc=(fn.__doc__ or "").strip())
        return fn
    return deco
