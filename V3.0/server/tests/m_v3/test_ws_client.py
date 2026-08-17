"""
OneBot 入站 WS 单测(V3.0 M-V3-2,2026-08-16):
1. _extract_content:array/string 两格式(文本+图片 url)
2. self_id 过滤:非接管号事件直接忽略(不触 redis)
3. 防抖合并→pipeline→adapter 下发 全链路(伪造 run_stream)
4. call_action:未连接抛 RuntimeError

作者: 李文煜
日期: 2026-08-16
"""
import asyncio
import json

import pytest

from core.config import settings


def _evt_array(user_id=111, self_id=999, text="你好", img=None):
    """构造 array 格式私聊事件"""
    segs = [{"type": "text", "data": {"text": text}}]
    if img:
        segs.append({"type": "image", "data": {"url": img}})
    return {"post_type": "message", "message_type": "private",
            "self_id": self_id, "user_id": user_id,
            "message_id": 42, "raw_message": text,
            "message": segs, "sender": {"nickname": "测试"}}


def test_extract_content_array():
    """array 格式:文本段拼接 + image url 提取"""
    from onebot.ws_client import _extract_content
    text, images = _extract_content(_evt_array(text="看这张", img="https://img.qq/1.jpg"))
    assert text == "看这张"
    assert images == ["https://img.qq/1.jpg"]


def test_extract_content_string_cq():
    """string 格式:去 CQ 码留纯文本 + CQ image url 正则抽取"""
    from onebot.ws_client import _extract_content
    data = {"post_type": "message", "message_type": "private",
            "self_id": 999, "user_id": 111,
            "raw_message": "看图 [CQ:image,file=x.jpg,url=https://g.chat/2.png] 好看吗",
            "message": "看图 [CQ:image,file=x.jpg,url=https://g.chat/2.png] 好看吗"}
    text, images = _extract_content(data)
    assert text == "看图  好看吗"
    assert images == ["https://g.chat/2.png"]


async def test_handle_event_filters_other_self_id(monkeypatch):
    """self_id 过滤:非接管号事件直接 return(不触 redis/takeover,炸即失败)"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "1145077465")

    async def boom(*a, **k):
        raise AssertionError("非接管号不应触 redis")

    monkeypatch.setattr("storage.redis_client.get_redis", boom)
    await ws_client._handle_event(_evt_array(self_id=3682822273))   # 非接管号:安全忽略


async def test_debounce_merge_and_deliver(monkeypatch):
    """防抖合并→pipeline→adapter 下发全链路:连发 3 条合并为一次 pipeline 调用,回复经 adapter 发出"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    monkeypatch.setattr(settings, "input_debounce_sec", 0.05)

    # redis:takeover 关闭(is_enabled False)
    class _FakeStore:
        async def is_enabled(self, redis, oid):
            return False
    monkeypatch.setattr("storage.takeover_store", _FakeStore(), raising=False)   # 子模块非 __init__ 导出

    async def fake_get_redis():
        class _R:
            pass
        return _R()
    monkeypatch.setattr("storage.redis_client.get_redis", fake_get_redis)

    # pipeline 替身:记录 user_text,产回复(async generator:run_stream 被 async for 消费)
    captured = []

    async def fake_run_stream(ctx):
        captured.append(ctx.user_text)
        ctx.reply_text = f"收到:{ctx.user_text}"
        yield ""   # 至少一个 yield 才是 async generator(async for 可消费)

    monkeypatch.setattr("onebot.ws_client.run_stream", fake_run_stream)   # 顶部 import,绑在 ws_client 命名空间

    # adapter 替身:记录下发
    sent = []

    class _FakeAdapter:
        async def send_text(self, oid, content, *, msg_id="", msg_seq=1, human_authored=False):
            sent.append((oid, content, msg_id))

    import adapter as adapter_mod
    monkeypatch.setattr(adapter_mod, "_current", _FakeAdapter())   # 单例注入,跳过工厂

    # 连发 3 条(防抖窗口内)
    await ws_client._schedule_debounce("111", "早", [], "m1")
    await ws_client._schedule_debounce("111", "中", [], "m2")
    await ws_client._schedule_debounce("111", "晚", [], "m3")
    await asyncio.sleep(0.4)   # 等 flush(0.05 防抖+pipeline 即时)

    assert len(captured) == 1                          # 合并为一次 pipeline
    assert "早" in captured[0] and "晚" in captured[0]  # 三条都进
    assert sent and sent[0][0] == "111"                # 回复经 adapter 发出
    assert sent[0][2] == "m3"                          # msg_id 用最新(分段门控)


async def test_call_action_not_connected():
    """call_action:NapCat 未连接抛 RuntimeError(调用方降级)"""
    from onebot import ws_client
    ws_client._ws = None
    with pytest.raises(RuntimeError):
        await ws_client.call_action("send_private_msg", {})


async def test_call_action_echo_match(monkeypatch):
    """call_action:echo tag 响应匹配(future 完成)"""
    from onebot import ws_client

    class _FakeWS:
        def __init__(self):
            self.sent = []

        async def send_text(self, raw):
            self.sent.append(json.loads(raw))
            # 模拟 NapCat 立即回响应(_dispatch_response 同步完成 future)
            resp = {"status": "ok", "retcode": 0, "echo": json.loads(raw)["echo"]}
            ws_client._dispatch_response(resp)

    ws_client._ws = _FakeWS()
    try:
        r = await ws_client.call_action("send_private_msg", {"user_id": 1}, timeout=2)
        assert r and r.get("status") == "ok"
    finally:
        ws_client._ws = None


async def test_handle_event_takeover_intercept(monkeypatch, fake_redis):
    """代答拦截(替代原 m8 webhook_takeover):代答模式开启时私聊消息入 pending 队列,不进 pipeline"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")

    enqueued = []

    class _FakeStore:
        async def is_enabled(self, redis, oid):
            return True

        async def enqueue(self, redis, oid, *, user_text, msg_id):
            enqueued.append((oid, user_text, msg_id))
            return f"pid-{len(enqueued)}"

    monkeypatch.setattr("storage.takeover_store", _FakeStore(), raising=False)

    async def boom_schedule(*a, **k):
        raise AssertionError("代答开启时不应进防抖/pipeline")

    monkeypatch.setattr(ws_client, "_schedule_debounce", boom_schedule)
    await ws_client._handle_event(_evt_array(user_id=111, self_id=999, text="在吗"))
    assert enqueued == [("111", "在吗", "42")]
