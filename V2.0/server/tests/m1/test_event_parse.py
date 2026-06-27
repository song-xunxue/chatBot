"""
C2C_MESSAGE_CREATE 事件解析 + 路由分发测试

作者: 李文煜
日期: 2026-06-25
"""
import json

from qq.webhook import parse_c2c_message


def test_parse_c2c_message_official_example():
    """解析 QQ 官方事件示例(对照 event.html DEMO d)"""
    d = {
        "author": {"user_openid": "E4F4AEA33253A2797FB897C50B81D7ED"},
        "content": "123",
        "id": "ROBOT1.0_.b6nx.CVryAO0nR58RXuU6SC.m92gc19j02qKqdm8ek!",
        "timestamp": "2023-11-06T13:37:18+08:00",
    }
    msg = parse_c2c_message(d)
    assert msg.openid == "E4F4AEA33253A2797FB897C50B81D7ED"
    assert msg.content == "123"
    assert msg.msg_id == "ROBOT1.0_.b6nx.CVryAO0nR58RXuU6SC.m92gc19j02qKqdm8ek!"
    assert msg.timestamp == "2023-11-06T13:37:18+08:00"
    assert msg.raw == d


def test_parse_c2c_message_missing_fields():
    """缺字段时安全降级(空串),不抛 KeyError"""
    msg = parse_c2c_message({})
    assert msg.openid == ""
    assert msg.content == ""
    assert msg.msg_id == ""


def test_webhook_c2c_schedules_debounce(make_signature, now_ts, fake_redis):
    """op=0 C2C_MESSAGE_CREATE:验签通过 → 立即返 ACK + 消息进防抖缓冲(M2:echo→防抖+pipeline)。
    pipeline 异步执行由 tests/m2/test_debounce 覆盖;此处验证 webhook 不阻塞立即 ACK + 防抖调度。"""
    from fastapi.testclient import TestClient
    from main import app
    from qq import webhook
    webhook._debounce.clear()   # 清理跨测试残留
    d = {"author": {"user_openid": "OID-ABC"}, "content": "你好", "id": "MID-1", "timestamp": "2023-11-06T13:37:18+08:00"}
    # body 与签名必须用同一序列化结果(确保验签通过)
    body = json.dumps({"op": 0, "s": 1, "t": "C2C_MESSAGE_CREATE", "d": d}, ensure_ascii=False).encode("utf-8")
    sig = make_signature(now_ts, body)
    headers = {"X-Signature-Ed25519": sig, "X-Signature-Timestamp": now_ts}
    with TestClient(app) as c:
        resp = c.post("/qq/webhook", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"op": 12}
    # M2:消息进防抖缓冲(不立即发;pipeline 由 _flush 异步执行,见 tests/m2/test_debounce)
    state = webhook._debounce.get("OID-ABC")
    assert state is not None, "消息应进防抖缓冲"
    assert "你好" in state["texts"]
    assert state["msg_id"] == "MID-1"
    webhook._debounce.clear()


def test_webhook_other_event_ignored(make_signature, now_ts, fake_redis):
    """op=0 但非 C2C_MESSAGE_CREATE(如 FRIEND_ADD)→ 忽略返 ACK,不触发 echo"""
    from fastapi.testclient import TestClient
    from main import app
    body = b'{"op":0,"s":2,"t":"FRIEND_ADD","d":{}}'
    sig = make_signature(now_ts, body)
    headers = {"X-Signature-Ed25519": sig, "X-Signature-Timestamp": now_ts}
    with TestClient(app) as c:
        resp = c.post("/qq/webhook", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"op": 12}


def test_webhook_missing_signature_rejected(now_ts, fake_redis):
    """普通事件缺签名头 → 401(防伪造)"""
    from fastapi.testclient import TestClient
    from main import app
    body = b'{"op":0,"s":3,"t":"C2C_MESSAGE_CREATE","d":{}}'
    with TestClient(app) as c:
        resp = c.post("/qq/webhook", content=body)  # 无签名头
    assert resp.status_code == 401


def test_webhook_expired_timestamp_rejected(make_signature, fake_redis):
    """时间戳超期 → 401(防重放)"""
    from fastapi.testclient import TestClient
    from main import app
    body = b'{"op":0,"s":4,"t":"C2C_MESSAGE_CREATE","d":{}}'
    old_ts = "1000000000"  # 1970 年,远超 300s 阈值
    sig = make_signature(old_ts, body)
    headers = {"X-Signature-Ed25519": sig, "X-Signature-Timestamp": old_ts}
    with TestClient(app) as c:
        resp = c.post("/qq/webhook", content=body, headers=headers)
    assert resp.status_code == 401
