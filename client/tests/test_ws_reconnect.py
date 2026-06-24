"""
WSClient 自动重连测试：mock websockets，验证失败重连 + auto_reconnect=False 只连一次 + _stop 退出。
并强化指数退避语义：不归零退避常量，断言退避序列增长、达到封顶后不再增长、成功连接后重置。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. 回填：mock websockets 覆盖重连/停止语义

2026-06-25
变更说明：
  1. 强化退避测试：不归零 _BACKOFF_*，断言退避序列增长(1,2,4..)、封顶后不增长、连上后重置
"""
import asyncio
import net.ws_client as wsc


def test_reconnects_until_stopped(monkeypatch, qapp):
    """失败重连，第 3 次连接触发 _stop → _main 退出，且确实重试了多次。
    归零退避仅用于这条"重试次数"用例（语义本就只验证重试次数）。"""
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


# --------------------------------------------------------------------------- #
# 强化：指数退避语义（不归零退避常量）
#
# 观测点：_main 的退避通过 asyncio.wait_for(self._stop.wait(), timeout=backoff) 实现。
# 这里 monkeypatch wsc.asyncio.wait_for：解析其 timeout 参数（即当前 backoff 值），
# 记录到序列后立即抛 asyncio.TimeoutError 模拟退避到期（不真实睡眠），从而观测到
# 完整的退避序列增长 / 封顶 / 重置，而不掩盖退避逻辑本身。
# --------------------------------------------------------------------------- #


def _patch_wait_for_to_capture_backoff(monkeypatch, captured):
    """把 wsc.asyncio.wait_for 替换为：捕获 timeout(=backoff) 并立即超时返回。

    captured: list，用于追加每次退避的 backoff 值。
    返回 None（_main 调用方拿到 TimeoutError 推进到下一轮重连）。
    """

    async def _fake_wait_for(awaitable, timeout):
        # 记录本次退避时长（即 _main 当前的 backoff 值）
        captured.append(timeout)
        # 模拟退避到期：直接抛 TimeoutError，不真实睡眠，也不 await 底层 awaitable
        raise asyncio.TimeoutError()

    monkeypatch.setattr(wsc.asyncio, "wait_for", _fake_wait_for)


def test_backoff_sequence_grows(monkeypatch, qapp):
    """连续失败：退避序列应指数增长（1, 2, 4, 8, ...），不被归零掩盖。"""
    # 保留真实退避常量（默认 _BACKOFF_INITIAL=1.0, _BACKOFF_FACTOR=2.0, _BACKOFF_MAX=30.0）
    ws = wsc.WSClient("ws://x", "t", "o")
    attempts = {"n": 0}
    backoffs = []

    class _FakeConnect:
        def __call__(self, *a, **k):
            return self

        async def __aenter__(self):
            attempts["n"] += 1
            # 失败 5 次后置 _stop，结束循环
            if attempts["n"] == 5:
                ws._stop.set()
            raise ConnectionRefusedError("refused")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(wsc.websockets, "connect", _FakeConnect())
    _patch_wait_for_to_capture_backoff(monkeypatch, backoffs)
    asyncio.run(ws._main())

    # 5 次失败，前 4 次进入退避（第 5 次置 _stop 后退出，不再退避）
    assert backoffs == [1.0, 2.0, 4.0, 8.0]


def test_backoff_caps_at_max(monkeypatch, qapp):
    """退避达到 _BACKOFF_MAX 后不再增长，持续保持封顶值。
    用小封顶值(4.0)加速验证：序列应为 1, 2, 4, 4, 4, ..."""
    monkeypatch.setattr(wsc, "_BACKOFF_MAX", 4.0)
    ws = wsc.WSClient("ws://x", "t", "o")
    attempts = {"n": 0}
    backoffs = []

    class _FakeConnect:
        def __call__(self, *a, **k):
            return self

        async def __aenter__(self):
            attempts["n"] += 1
            if attempts["n"] == 7:
                ws._stop.set()
            raise ConnectionRefusedError("refused")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(wsc.websockets, "connect", _FakeConnect())
    _patch_wait_for_to_capture_backoff(monkeypatch, backoffs)
    asyncio.run(ws._main())

    # 7 次失败：前 6 次退避；1→2→4(封顶)→4→4→4
    assert backoffs == [1.0, 2.0, 4.0, 4.0, 4.0, 4.0]
    # 断言封顶生效：序列中不应出现大于 _BACKOFF_MAX(4.0) 的值
    assert all(b <= 4.0 for b in backoffs)


def test_backoff_resets_after_successful_connect(monkeypatch, qapp):
    """成功连接后退避应重置回 _BACKOFF_INITIAL；再次失败时退避从初始值重新增长。"""
    ws = wsc.WSClient("ws://x", "t", "o")
    attempts = {"n": 0}
    backoffs = []

    class _FakeConnect:
        def __call__(self, *a, **k):
            return self

        async def __aenter__(self):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                # 前 2 次失败 → 退避 1.0, 2.0
                raise ConnectionRefusedError("refused")
            if attempts["n"] == 3:
                # 第 3 次成功连入：_main 会重置 backoff=INITIAL 并进入收发协程
                return self
            # 不会再走到这里
            raise AssertionError("unexpected 4th attempt")

        async def __aexit__(self, *a):
            # 成功连接后 _receiver/_sender 立即结束（_sender 从空队列取不到消息，
            # 用 _stop 让 gather 退出，从而进入断线→退避分支，验证重置后的退避）
            return False

    monkeypatch.setattr(wsc.websockets, "connect", _FakeConnect())

    # 让 _sender 在成功连接后立即结束（用空实现替代真实发送循环），避免测试挂起
    async def _sender_drain(ws_ctx):
        await asyncio.sleep(0)

    monkeypatch.setattr(wsc.WSClient, "_sender", _sender_drain)

    # wait_for 仅在第 3 次调用（成功重置后的那一次退避）后置 _stop 以结束循环；
    # 前两次调用只是捕获并立即超时推进重试。
    async def _fake_wait_for(awaitable, timeout):
        backoffs.append(timeout)
        if len(backoffs) == 3:
            ws._stop.set()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(wsc.asyncio, "wait_for", _fake_wait_for)

    asyncio.run(ws._main())

    # 前 2 次失败：退避 1.0, 2.0；第 3 次成功连接后 backoff 重置；断线后第 1 次退避回到 1.0
    assert backoffs == [1.0, 2.0, 1.0]
