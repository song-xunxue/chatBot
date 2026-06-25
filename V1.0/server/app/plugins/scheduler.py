"""
on_tick 调度器 TickScheduler
周期性对每个活跃 object_id 触发 on_tick 钩子，驱动 mood_dynamic/time_aware/proactive_msg 等定时插件。
间隔由 settings.plugin_tick_interval 控制。tick_once 供测试立即触发。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 创建调度器：start/stop/_loop/tick_once
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class TickScheduler:
    def __init__(self, bus, registry, interval: float = 60.0):
        self._bus = bus
        self._registry = registry
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def _loop(self):
        """主循环：每 interval 秒对每个活跃对象触发一次 on_tick"""
        from plugins.base import ON_TICK
        from pipeline.context import MessageContext
        while True:
            await asyncio.sleep(self._interval)
            try:
                for oid in self._registry.object_ids():
                    await self._bus.fire(ON_TICK, MessageContext(object_id=oid))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("tick loop iteration failed")

    def start(self) -> None:
        """启动调度循环（幂等：已运行则不重复）"""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """停止调度循环并等待取消完成"""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def tick_once(self) -> None:
        """立即对每个活跃对象触发一轮 on_tick（供测试，绕过 sleep）"""
        from plugins.base import ON_TICK
        from pipeline.context import MessageContext
        for oid in self._registry.object_ids():
            await self._bus.fire(ON_TICK, MessageContext(object_id=oid))
