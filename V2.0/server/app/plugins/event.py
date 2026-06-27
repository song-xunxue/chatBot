"""
事件总线 EventBus
按 priority 升序分发钩子;单插件异常隔离(捕获记录后跳过,不影响其他插件与主流程);
任一插件返回 STOP 则停止后续分发。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 EventBus 到 V2.0(零业务改动;subscribe/fire + 优先级 + STOP + 异常隔离)
"""
import logging
from dataclasses import dataclass

from plugins.base import HookResult

logger = logging.getLogger(__name__)


@dataclass
class _Subscription:
    """一条钩子订阅:插件名 + 优先级 + 回调"""
    hook_name: str
    plugin_name: str
    priority: int        # 小先执行
    callback: object     # async (ctx) -> HookResult | None


class EventBus:
    """事件总线:维护各钩子的订阅列表,fire 时按优先级升序分发。"""

    def __init__(self):
        self._subs: dict[str, list[_Subscription]] = {}

    def subscribe(self, hook_name: str, plugin_name: str, priority: int, callback) -> None:
        """订阅钩子。
        幂等:同一 (hook, plugin) 重复订阅先移除旧项再插入,避免 reload 后重复触发。"""
        lst = self._subs.setdefault(hook_name, [])
        lst = [s for s in lst if s.plugin_name != plugin_name]
        lst.append(_Subscription(hook_name, plugin_name, priority, callback))
        lst.sort(key=lambda s: s.priority)   # 始终按优先级升序,fire 时无需再排
        self._subs[hook_name] = lst

    def unsubscribe_plugin(self, plugin_name: str) -> None:
        """移除某插件在所有钩子上的订阅(unload/disable/reload 时调用)"""
        for hook_name in list(self._subs.keys()):
            self._subs[hook_name] = [s for s in self._subs[hook_name] if s.plugin_name != plugin_name]

    def clear(self) -> None:
        self._subs.clear()

    def subscribers(self, hook_name: str) -> list[_Subscription]:
        """返回某钩子的订阅快照(按优先级升序)"""
        return list(self._subs.get(hook_name, []))

    async def fire(self, hook_name: str, ctx) -> str:
        """触发钩子:按优先级调用订阅者。
        - 异常隔离:单个回调抛错 → 记录后跳过该插件,不影响其他插件与主流程。
        - STOP:任一订阅者返回 STOP → 停止调用后续订阅者并返回 STOP。
        - 无订阅 / 全部 CONTINUE → 返回 CONTINUE。"""
        result = HookResult.CONTINUE
        for sub in self.subscribers(hook_name):   # 取快照,避免遍历中结构变更
            try:
                r = await sub.callback(ctx)
            except Exception:
                logger.exception("plugin %s hook %s raised, isolated and skipped",
                                 sub.plugin_name, hook_name)
                continue
            if r == HookResult.STOP:
                result = HookResult.STOP
                break
        return result
