"""
proactive_msg 插件测试：概率+冷却触发广播(含 nudge)、冷却内不重复。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 覆盖 proactive_msg：触发/冷却
"""
from plugins.base import ON_TICK
from plugins.connections import get_connection_registry


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, m):
        self.sent.append(m)


def _ctx(oid="o1"):
    return type("C", (), {"object_id": oid, "plugin_meta": {}})()


async def test_proactive_sends_when_triggered(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("proactive_msg", True)
    await real_manager.set_object_config("proactive_msg", "o1", True,
                                         {"probability": 1.0, "cooldown_sec": 0})
    reg = get_connection_registry()
    reg._conns.clear()
    ws = _FakeWS()
    reg.register("o1", ws)
    try:
        await real_manager._bus.fire(ON_TICK, _ctx())
        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "proactive_msg"
        assert ws.sent[0]["payload"]["nudge"] is True
    finally:
        reg._conns.clear()


async def test_cooldown_blocks_rapid_repeat(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("proactive_msg", True)
    await real_manager.set_object_config("proactive_msg", "o1", True,
                                         {"probability": 1.0, "cooldown_sec": 3600})
    reg = get_connection_registry()
    reg._conns.clear()
    ws = _FakeWS()
    reg.register("o1", ws)
    try:
        await real_manager._bus.fire(ON_TICK, _ctx())
        assert len(ws.sent) == 1
        await real_manager._bus.fire(ON_TICK, _ctx())     # 冷却内
        assert len(ws.sent) == 1                           # 不重复打扰
    finally:
        reg._conns.clear()
