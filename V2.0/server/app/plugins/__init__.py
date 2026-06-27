"""
插件系统单例与生命周期入口
get_event_bus() / get_plugin_manager() 供 pipeline runner 取用(未初始化返回 None → runner 跳过钩子)。
init_plugins() 在 main.py lifespan 启动阶段调用;shutdown_plugins() 关闭阶段调用。

M2 阶段:plugin_dir 内无业务插件(manifest 扫描子目录为空),总线空载但可用,
pipeline 的 bus.fire 无订阅即 CONTINUE,保证钩子链路通。业务插件(M6 .star 兼容层)后续加载。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植插件单例管理到 V2.0(零业务改动)
"""
from pathlib import Path

from redis.asyncio import Redis

from core.config import settings, PROJECT_ROOT
from plugins.event import EventBus
from plugins.manager import PluginManager

_manager: PluginManager | None = None
_bus: EventBus | None = None


def get_event_bus() -> EventBus | None:
    """取全局事件总线;未初始化返回 None(pipeline 据此跳过钩子,降级为无插件行为)"""
    return _bus


def get_plugin_manager() -> PluginManager | None:
    return _manager


def _resolve_plugin_dir() -> Path:
    """解析插件根目录:绝对路径直接用,相对路径拼到项目根"""
    p = Path(settings.plugin_dir)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


async def init_plugins(redis: Redis) -> PluginManager | None:
    """初始化插件系统:建总线 + 管理器,发现并加载全部插件、注册钩子。
    plugin_enabled=False → 不初始化(总线置 None),返回 None。
    无插件目录或无插件时返回空载管理器(总线仍可用,fire 无订阅即 CONTINUE)。"""
    global _manager, _bus
    if not settings.plugin_enabled:
        _manager = None
        _bus = None
        return None
    _bus = EventBus()
    _manager = PluginManager(redis, _bus, _resolve_plugin_dir())
    if settings.plugin_auto_discover:
        await _manager.load_all()
    return _manager


async def shutdown_plugins() -> None:
    """关闭:卸载全部插件、清空单例"""
    global _manager, _bus
    if _manager is not None:
        await _manager.unload_all()
    _manager = None
    _bus = None
