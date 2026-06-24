"""
EventBus 单测：优先级升序、STOP 中断、异常隔离、无订阅、取消订阅、幂等订阅

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.1 覆盖 EventBus 分发语义
"""
from types import SimpleNamespace

from plugins.event import EventBus
from plugins.base import HookResult, ON_AFTER_LLM


def _ctx():
    return SimpleNamespace(object_id="o1", calls=[])


async def test_priority_ascending():
    bus = EventBus()
    ctx = _ctx()
    async def a(ctx): ctx.calls.append("a"); return HookResult.CONTINUE
    async def b(ctx): ctx.calls.append("b"); return HookResult.CONTINUE
    async def c(ctx): ctx.calls.append("c"); return HookResult.CONTINUE
    bus.subscribe(ON_AFTER_LLM, "a", 200, a)
    bus.subscribe(ON_AFTER_LLM, "b", 50, b)
    bus.subscribe(ON_AFTER_LLM, "c", 100, c)
    res = await bus.fire(ON_AFTER_LLM, ctx)
    assert res == HookResult.CONTINUE
    assert ctx.calls == ["b", "c", "a"]      # 50,100,200 升序


async def test_stop_breaks_chain():
    bus = EventBus()
    ctx = _ctx()
    async def first(ctx): ctx.calls.append("first"); return HookResult.STOP
    async def second(ctx): ctx.calls.append("second"); return HookResult.CONTINUE
    bus.subscribe(ON_AFTER_LLM, "first", 10, first)
    bus.subscribe(ON_AFTER_LLM, "second", 20, second)
    res = await bus.fire(ON_AFTER_LLM, ctx)
    assert res == HookResult.STOP
    assert ctx.calls == ["first"]            # STOP 后 second 不执行


async def test_exception_isolation():
    bus = EventBus()
    ctx = _ctx()
    async def boom(ctx): raise RuntimeError("boom")
    async def ok(ctx): ctx.calls.append("ok"); return HookResult.CONTINUE
    bus.subscribe(ON_AFTER_LLM, "boom", 10, boom)
    bus.subscribe(ON_AFTER_LLM, "ok", 20, ok)
    res = await bus.fire(ON_AFTER_LLM, ctx)
    assert res == HookResult.CONTINUE         # 异常不影响最终结果
    assert ctx.calls == ["ok"]                # 后续插件仍执行


async def test_no_subscribers_returns_continue():
    bus = EventBus()
    assert await bus.fire(ON_AFTER_LLM, _ctx()) == HookResult.CONTINUE


async def test_unsubscribe_plugin():
    bus = EventBus()
    ctx = _ctx()
    async def cb(ctx): ctx.calls.append("x"); return HookResult.CONTINUE
    bus.subscribe(ON_AFTER_LLM, "x", 10, cb)
    bus.unsubscribe_plugin("x")
    await bus.fire(ON_AFTER_LLM, ctx)
    assert ctx.calls == []


async def test_subscribe_idempotent():
    """同名插件重复订阅只保留一条（reload 安全）"""
    bus = EventBus()
    n = {"v": 0}
    async def cb(ctx): n["v"] += 1; return HookResult.CONTINUE
    bus.subscribe(ON_AFTER_LLM, "x", 10, cb)
    bus.subscribe(ON_AFTER_LLM, "x", 10, cb)
    await bus.fire(ON_AFTER_LLM, _ctx())
    assert n["v"] == 1
