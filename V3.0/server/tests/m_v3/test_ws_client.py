"""
OneBot 入站 WS 单测(V3.0 M-V3-2,2026-08-16):
1. _extract_content:array/string 两格式(文本+图片 url)
2. self_id 过滤:非接管号事件直接忽略(不触 redis)
3. 防抖合并→pipeline→adapter 下发 全链路(伪造 run_stream)
4. call_action:未连接抛 RuntimeError
5. message_sent 手动回复(2026-09-07):自己发送去重/手动触发记录/群聊忽略/语音占位/竞态等待

作者: 李文煜
日期: 2026-08-16

2026-09-07
变更说明：
  1. 新增 message_sent 用例:_handle_manual_sent(自己发忽略/手动触发 record_manual_reply/
     群聊忽略/语音[语音]占位)+ call_action 记录 message_id + _confirm_own_send 竞态等待
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


# ================ message_sent 手动回复(2026-09-07)================

def _evt_sent(user_id=111, self_id=999, text="手动回", msg_id=777, mtype="private", segs=None,
              target_id=None):
    """构造 array 格式自身发送事件(reportSelfMessage 开启后 NapCat 上报)。
    NapCat 实测形状(2026-09-07 线上验证):user_id=senderUin(发送者=自己),
    接收方在 target_id(peerUin)——target_id=None 时不上报该字段(兜底走 user_id)。"""
    evt = {"post_type": "message_sent", "message_type": mtype,
           "self_id": self_id, "user_id": user_id, "message_id": msg_id,
           "time": 1757200000,                       # 秒(OneBot 事件 time 字段)
           "raw_message": text,
           "message": segs if segs is not None else [{"type": "text", "data": {"text": text}}],
           "sender": {"nickname": "清浔"}}
    if target_id is not None:
        evt["target_id"] = target_id
    return evt


def _boom_record(monkeypatch):
    """替身:record_manual_reply 被调即断言失败"""
    async def boom(*a, **k):
        raise AssertionError("不应触发手动回复记录")
    monkeypatch.setattr("takeover.service.record_manual_reply", boom)


def _inject_redis(monkeypatch, fake):
    """把 fakeredis 接到 get_redis(m_v3 夹具不注入 redis_client 单例,须显式接)"""
    async def _get():
        return fake
    monkeypatch.setattr("storage.redis_client.get_redis", _get)


async def _seed_history(fake_redis):
    """给 oid=111 预置一条会话历史(过陌生人门控)"""
    from storage import chat_store
    await chat_store.append_message(fake_redis, "111", sender="user", content="hi")


async def test_message_sent_own_send_ignored(monkeypatch):
    """服务器自己发送(msg_id 命中 _sent_msg_ids)→ 忽略,不触发记录(pipeline 已落库)"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._sent_msg_ids["777"] = 1.0
    _boom_record(monkeypatch)
    try:
        await ws_client._handle_event(_evt_sent(msg_id=777))   # 命中自己发送
    finally:
        ws_client._sent_msg_ids.clear()


async def test_message_sent_group_ignored(monkeypatch):
    """自己发的群聊消息忽略(只在私聊代答场景)"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    _boom_record(monkeypatch)
    try:
        await ws_client._handle_event(_evt_sent(mtype="group", msg_id=778))
    finally:
        ws_client._sent_msg_ids.clear()


async def test_message_sent_other_self_id_ignored(monkeypatch):
    """非接管号的 message_sent 忽略(self_id 过滤同普通消息)"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    _boom_record(monkeypatch)
    try:
        await ws_client._handle_event(_evt_sent(self_id=3682822273, msg_id=779))
    finally:
        ws_client._sent_msg_ids.clear()


async def test_message_sent_manual_triggers_record(monkeypatch, fake_redis):
    """管理员手动回复(msg_id 未命中)→ record_manual_reply(接收方 oid/内容/秒→毫秒 ts)"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0
    _inject_redis(monkeypatch, fake_redis)
    await _seed_history(fake_redis)
    captured = {}

    async def fake_record(redis, oid, content, *, sent_ts=0):
        captured.update(oid=oid, content=content, sent_ts=sent_ts)
        return {"proxy_mid": "m1", "archived_pendings": 0, "scored": False}

    monkeypatch.setattr("takeover.service.record_manual_reply", fake_record)
    try:
        await ws_client._handle_event(_evt_sent(msg_id=888, text="嗯嗯在的~"))
    finally:
        ws_client._sent_msg_ids.clear()
    assert captured["oid"] == "111"                    # 私聊 message_sent:user_id=接收方
    assert captured["content"] == "嗯嗯在的~"
    assert captured["sent_ts"] == 1757200000000        # 事件 time 秒→毫秒


async def test_message_sent_voice_placeholder(monkeypatch, fake_redis):
    """纯语音手动回复 → [语音] 占位落库(内容不可还原,保上下文)"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0
    _inject_redis(monkeypatch, fake_redis)
    await _seed_history(fake_redis)
    captured = {}

    async def fake_record(redis, oid, content, *, sent_ts=0):
        captured["content"] = content
        return {"proxy_mid": "m1", "archived_pendings": 0, "scored": False}

    monkeypatch.setattr("takeover.service.record_manual_reply", fake_record)
    evt = _evt_sent(msg_id=889, text="",
                    segs=[{"type": "record", "data": {"file": "x.silk"}}])
    evt["raw_message"] = "[CQ:record,file=x.silk]"
    try:
        await ws_client._handle_event(evt)
    finally:
        ws_client._sent_msg_ids.clear()
    assert captured["content"] == "[语音]"


async def test_call_action_records_sent_msg_id():
    """call_action:send_private_msg 成功响应的 message_id 进去重集(供 message_sent 判自己发送)"""
    from onebot import ws_client

    class _FakeWS:
        async def send_text(self, raw):
            req = json.loads(raw)
            resp = {"status": "ok", "retcode": 0, "echo": req["echo"],
                    "data": {"message_id": 12345}}
            ws_client._dispatch_response(resp)

    ws_client._ws = _FakeWS()
    ws_client._sent_msg_ids.clear()
    try:
        r = await ws_client.call_action("send_private_msg", {"user_id": 1}, timeout=2)
        assert r and r.get("status") == "ok"
        assert "12345" in ws_client._sent_msg_ids       # 已记录
        assert ws_client._inflight_sends == 0           # 在途计数归零
    finally:
        ws_client._ws = None
        ws_client._sent_msg_ids.clear()


async def test_confirm_own_send_race_wait(monkeypatch):
    """竞态:message_sent 先到、Action 响应后落定 → _confirm_own_send 等待后正确判为自己发送"""
    from onebot import ws_client
    monkeypatch.setattr(ws_client, "_SENT_RACE_ROUNDS", 20)
    monkeypatch.setattr(ws_client, "_SENT_RACE_STEP", 0.01)
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 1

    async def late_record():
        await asyncio.sleep(0.02)                       # 模拟响应 20ms 后落定
        ws_client._sent_msg_ids["555"] = 1.0
        ws_client._inflight_sends = 0

    task = asyncio.get_event_loop().create_task(late_record())
    try:
        ok = await ws_client._confirm_own_send("555")   # 事件先到:等待后命中
        assert ok is True
        await task
    finally:
        ws_client._sent_msg_ids.clear()
        ws_client._inflight_sends = 0


async def test_confirm_own_send_no_inflight_fast_false():
    """无在途发送:未知 msg_id 立即判 False(手动回复),不空等"""
    from onebot import ws_client
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0
    assert await ws_client._confirm_own_send("999999") is False


async def test_dispatch_response_records_late_send():
    """审查修复:_dispatch_response 经 _send_tags 同步记录 send 响应 message_id——
    call_action 超时/迟到响应(future 已弃)时也能记,防自发消息 message_sent 误判手动"""
    from onebot import ws_client
    ws_client._sent_msg_ids.clear()
    ws_client._send_tags.clear()
    ws_client._send_tags["act-99"] = 1.0
    consumed = ws_client._dispatch_response(
        {"echo": "act-99", "status": "ok", "retcode": 0, "data": {"message_id": 777}})
    assert consumed is True
    assert "777" in ws_client._sent_msg_ids        # 迟到响应也登记
    assert "act-99" not in ws_client._send_tags    # tag 已消费
    ws_client._sent_msg_ids.clear()


async def test_dispatch_response_failed_send_not_recorded():
    """失败的 send 响应(retcode!=0,消息没发出去)不登记 message_id"""
    from onebot import ws_client
    ws_client._sent_msg_ids.clear()
    ws_client._send_tags.clear()
    ws_client._send_tags["act-98"] = 1.0
    ws_client._dispatch_response(
        {"echo": "act-98", "status": "failed", "retcode": 1200, "data": {"message_id": 778}})
    assert "778" not in ws_client._sent_msg_ids
    ws_client._send_tags.clear()


async def test_message_sent_target_id_recipient(monkeypatch, fake_redis):
    """线上实测修复(2026-09-07):NapCat message_sent 的 user_id=发送者(自己),接收方在
    target_id——按真实形状(user_id=self,target_id=主号)应记录到 target_id 的 oid"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0
    _inject_redis(monkeypatch, fake_redis)
    await _seed_history(fake_redis)
    captured = {}

    async def fake_record(redis, oid, content, *, sent_ts=0):
        captured["oid"] = oid
        return {"proxy_mid": "m", "archived_pendings": 0, "scored": False}
    monkeypatch.setattr("takeover.service.record_manual_reply", fake_record)
    try:
        await ws_client._handle_event(
            _evt_sent(user_id=999, target_id=111, msg_id=895))   # user_id=自己,target_id=接收方
    finally:
        ws_client._sent_msg_ids.clear()
    assert captured["oid"] == "111"                   # 记录到接收方,不是自己


async def test_message_sent_self_loop_skipped(monkeypatch, fake_redis):
    """user_id 与 target_id 均解析为自己(无法定位接收方)→ 跳过不记录"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0
    _inject_redis(monkeypatch, fake_redis)

    async def boom(*a, **k):
        raise AssertionError("无法定位接收方时不应触发记录")
    monkeypatch.setattr("takeover.service.record_manual_reply", boom)
    await ws_client._handle_event(_evt_sent(user_id=999, msg_id=896))   # user_id=self,无 target_id
    ws_client._sent_msg_ids.clear()
    """审查修复:陌生人门控——oid 无会话/代答/待答时 message_sent 不记录(不凭空建会话)"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0

    async def boom(*a, **k):
        raise AssertionError("陌生 oid 不应触发记录")
    monkeypatch.setattr("takeover.service.record_manual_reply", boom)
    _inject_redis(monkeypatch, fake_redis)
    await ws_client._handle_event(_evt_sent(msg_id=890, user_id=999999))   # 陌生 oid
    ws_client._sent_msg_ids.clear()


async def test_message_sent_stranger_with_history_recorded(monkeypatch, fake_redis):
    """门控放行:oid 已有会话历史 → 正常记录"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0
    _inject_redis(monkeypatch, fake_redis)
    await _seed_history(fake_redis)
    captured = {}

    async def fake_record(redis, oid, content, *, sent_ts=0):
        captured["oid"] = oid
        return {"proxy_mid": "m", "archived_pendings": 0, "scored": False}
    monkeypatch.setattr("takeover.service.record_manual_reply", fake_record)
    await ws_client._handle_event(_evt_sent(msg_id=891))
    assert captured["oid"] == "111"
    ws_client._sent_msg_ids.clear()


async def test_message_sent_face_placeholder(monkeypatch, fake_redis):
    """占位扩展:纯表情(face)手动回复 → [表情] 占位落库"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0
    _inject_redis(monkeypatch, fake_redis)
    await _seed_history(fake_redis)
    captured = {}

    async def fake_record(redis, oid, content, *, sent_ts=0):
        captured["content"] = content
        return {"proxy_mid": "m", "archived_pendings": 0, "scored": False}
    monkeypatch.setattr("takeover.service.record_manual_reply", fake_record)
    evt = _evt_sent(msg_id=892, text="",
                    segs=[{"type": "face", "data": {"id": "1"}}])
    evt["raw_message"] = "[CQ:face,id=1]"
    await ws_client._handle_event(evt)
    assert captured["content"] == "[表情]"
    ws_client._sent_msg_ids.clear()


async def test_message_sent_string_cq_voice(monkeypatch, fake_redis):
    """占位扩展:string(CQ 码)格式上报的纯语音 → [语音](原只认 array 格式)"""
    from onebot import ws_client
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    ws_client._sent_msg_ids.clear()
    ws_client._inflight_sends = 0
    _inject_redis(monkeypatch, fake_redis)
    await _seed_history(fake_redis)
    captured = {}

    async def fake_record(redis, oid, content, *, sent_ts=0):
        captured["content"] = content
        return {"proxy_mid": "m", "archived_pendings": 0, "scored": False}
    monkeypatch.setattr("takeover.service.record_manual_reply", fake_record)
    evt = _evt_sent(msg_id=893, text="", segs=None)
    evt["message"] = "[CQ:record,file=x.silk]"
    evt["raw_message"] = "[CQ:record,file=x.silk]"
    await ws_client._handle_event(evt)
    assert captured["content"] == "[语音]"
    ws_client._sent_msg_ids.clear()


async def test_inbound_image_enqueue_placeholder(monkeypatch, fake_redis):
    """审查修复:代答模式下纯图片消息占位入队(原空文本,归档/合并时丢消息)"""
    from onebot import ws_client
    from storage import takeover_store
    monkeypatch.setattr(settings, "onebot_self_id", "999")
    _inject_redis(monkeypatch, fake_redis)
    await takeover_store.set_enabled(fake_redis, "111", True)
    evt = {"post_type": "message", "message_type": "private",
           "self_id": 999, "user_id": 111, "message_id": 55,
           "raw_message": "",
           "message": [{"type": "image", "data": {"url": "https://img.qq/1.jpg"}}],
           "sender": {"nickname": "测试"}}
    await ws_client._handle_event(evt)
    q = await takeover_store.list_queue(fake_redis, "111")
    assert len(q) == 1 and q[0]["user_text"] == "[图片]"   # 占位入队,不再空文本
