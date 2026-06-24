"""
插件系统单例与生命周期入口
get_event_bus() / get_plugin_manager() 供 runner 与 REST 取用（未初始化返回 None → runner 跳过钩子，保持向后兼容）。
init_plugins() 在 main.py lifespan 启动阶段调用；shutdown_plugins() 关闭阶段调用。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.1 创建插件系统单例管理（init/get/shutdown）
"""
from pathlib import Path

from redis.asyncio import Redis

from core.config import settings, PROJECT_ROOT
from plugins.event import EventBus
from plugins.manager import PluginManager

_manager: PluginManager | None = None
_bus: EventBus | None = None


def get_event_bus() -> EventBus | None:
    """取全局事件总线；未初始化返回 None（runner 据此跳过钩子，降级为无插件行为）"""
    return _bus


def get_plugin_manager() -> PluginManager | None:
    return _manager


def _resolve_plugin_dir() -> Path:
    """解析插件根目录：绝对路径直接用，相对路径拼到项目根"""
    p = Path(settings.plugin_dir)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


async def init_plugins(redis: Redis) -> PluginManager | None:
    """初始化插件系统：建总线 + 管理器，发现并加载全部插件、注册钩子。
    plugin_enabled=False → 不初始化（总线置 None），返回 None。
    无插件目录或无插件时返回空载管理器（总线仍可用，fire 无订阅即 CONTINUE）。"""
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
    """关闭：卸载全部插件、清空单例"""
    global _manager, _bus
    if _manager is not None:
        await _manager.unload_all()
    _manager = None
    _bus = None
