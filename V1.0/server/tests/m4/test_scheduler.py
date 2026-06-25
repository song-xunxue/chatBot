"""
TickScheduler 测试：tick_once 对每个活跃对象触发 on_tick；start/stop 生命周期。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 覆盖调度器：tick_once/start/stop
"""
from plugins.event import EventBus
from plugins.scheduler import TickScheduler
from plugins.connections import ConnectionRegistry
from plugins.base import ON_TICK, HookResult


class _FakeWS:
    async def send_json(self, m):
        pass


async def test_tick_once_fires_per_object():
    bus = EventBus()
    reg = ConnectionRegistry()
    reg.register("o1", _FakeWS())
    reg.register("o2", _FakeWS())
    fired = []

    async def cb(ctx):
        fired.append(ctx.object_id)
        return HookResult.CONTINUE

    bus.subscribe(ON_TICK, "t", 100, cb)
    sched = TickScheduler(bus, reg, interval=999)
    await sched.tick_once()
    assert sorted(fired) == ["o1", "o2"]


async def test_start_stop():
    bus = EventBus()
    reg = ConnectionRegistry()
    sched = TickScheduler(bus, reg, interval=0.01)
    sched.start()
    assert sched._task is not None and not sched._task.done()
    await sched.stop()
    assert sched._task is None or sched._task.done()


async def test_tick_once_no_subscribers_noop():
    """无 on_tick 订阅者时 tick_once 不报错"""
    bus = EventBus()
    reg = ConnectionRegistry()
    reg.register("o1", _FakeWS())
    sched = TickScheduler(bus, reg)
    await sched.tick_once()   # 不抛异常即可
