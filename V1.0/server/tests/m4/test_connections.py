"""
ConnectionRegistry 测试：register/broadcast/deregister、失败连接隔离移除。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 覆盖连接注册表
"""
from plugins.connections import ConnectionRegistry


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, m):
        self.sent.append(m)


class _BadWS:
    async def send_json(self, m):
        raise RuntimeError("closed")


async def test_register_broadcast_deregister():
    reg = ConnectionRegistry()
    w1, w2 = _FakeWS(), _FakeWS()
    reg.register("o1", w1)
    reg.register("o1", w2)
    reg.register("o2", _FakeWS())
    assert set(reg.object_ids()) == {"o1", "o2"}
    n = await reg.broadcast("o1", {"x": 1})
    assert n == 2
    assert w1.sent == [{"x": 1}] and w2.sent == [{"x": 1}]
    reg.deregister(w1)
    n = await reg.broadcast("o1", {"y": 2})
    assert n == 1                                   # w1 已注销


async def test_broadcast_isolates_failed_connection():
    reg = ConnectionRegistry()
    bad, good = _BadWS(), _FakeWS()
    reg.register("o1", bad)
    reg.register("o1", good)
    n = await reg.broadcast("o1", {"z": 1})
    assert n == 1                                   # bad 失败被移除，good 成功
    assert good.sent == [{"z": 1}]
    n2 = await reg.broadcast("o1", {"z": 2})
    assert n2 == 1                                  # bad 已不在
