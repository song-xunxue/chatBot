"""
on_tick 调度器 TickScheduler
周期性对每个活跃 object_id 触发 on_tick 钩子,驱动 mood 衰减等定时任务。
间隔由 settings.plugin_tick_interval 控制。tick_once 供测试立即触发。

V2.0 改造(M2):V1.0 依赖 ConnectionRegistry(WebSocket 活跃对象),但 V2.0 砍了 WS 客户端、
改用 QQ REST。改为注入 object_ids_provider 回调(返回需 tick 的 object_id 列表),
由 mood/主动消息等模块自行提供活跃对象来源。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 scheduler 到 V2.0,改造:ConnectionRegistry(WS) → object_ids_provider 回调
     (V2.0 无 WS 客户端,mood 衰减由 mood 模块提供活跃 oid 列表)
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class TickScheduler:
    def __init__(self, bus, object_ids_provider=None, interval: float = 60.0):
        """
        参数:
            bus: EventBus,触发 ON_TICK 钩子
            object_ids_provider: 返回需 tick 的 object_id 列表;可为同步 list 或 async 函数(默认空)
            interval: tick 周期秒
        """
        self._bus = bus
        self._provider = object_ids_provider or (lambda: [])
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def _resolve_oids(self) -> list[str]:
        """调用 provider 取 object_id 列表(兼容同步/异步 provider)"""
        if asyncio.iscoroutinefunction(self._provider):
            return list(await self._provider() or [])
        return list(self._provider() or [])

    async def _loop(self):
        """主循环:每 interval 秒对每个活跃对象触发一次 on_tick"""
        from plugins.base import ON_TICK
        from pipeline.context import MessageContext
        while True:
            await asyncio.sleep(self._interval)
            try:
                for oid in await self._resolve_oids():
                    await self._bus.fire(ON_TICK, MessageContext(object_id=oid))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("tick loop iteration failed")

    def start(self) -> None:
        """启动调度循环(幂等:已运行则不重复)"""
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
        """立即对每个活跃对象触发一轮 on_tick(供测试,绕过 sleep)"""
        from plugins.base import ON_TICK
        from pipeline.context import MessageContext
        for oid in await self._resolve_oids():
            await self._bus.fire(ON_TICK, MessageContext(object_id=oid))
