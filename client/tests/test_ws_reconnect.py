"""
WSClient 自动重连测试：mock websockets，验证失败重连 + auto_reconnect=False 只连一次 + _stop 退出。
回填 M5 缺口（之前未测重连逻辑）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. 回填：mock websockets 覆盖重连/停止语义
"""
import asyncio
import net.ws_client as wsc


def test_reconnects_until_stopped(monkeypatch, qapp):
    """失败重连，第 3 次连接触发 _stop → _main 退出，且确实重试了多次"""
    ws = wsc.WSClient("ws://x", "t", "o")
    calls = {"n": 0}

    class _FakeConnect:
        def __call__(self, *a, **k):
            return self

        async def __aenter__(self):
            calls["n"] += 1
            if calls["n"] == 3:
                ws._stop.set()
            raise ConnectionRefusedError("refused")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(wsc.websockets, "connect", _FakeConnect())
    monkeypatch.setattr(wsc, "_BACKOFF_INITIAL", 0.0)
    monkeypatch.setattr(wsc, "_BACKOFF_MAX", 0.0)
    asyncio.run(ws._main())
    assert calls["n"] == 3          # 失败重试到第 3 次


def test_no_reconnect_when_disabled(monkeypatch, qapp):
    """auto_reconnect=False：连接失败后不重试"""
    ws = wsc.WSClient("ws://x", "t", "o", auto_reconnect=False)
    calls = {"n": 0}

    class _FakeConnect:
        def __call__(self, *a, **k):
            return self

        async def __aenter__(self):
            calls["n"] += 1
            raise ConnectionRefusedError("refused")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(wsc.websockets, "connect", _FakeConnect())
    monkeypatch.setattr(wsc, "_BACKOFF_INITIAL", 0.0)
    monkeypatch.setattr(wsc, "_BACKOFF_MAX", 0.0)
    asyncio.run(ws._main())
    assert calls["n"] == 1          # 只尝试一次
