"""
shared/protocol 纯函数测试
验证 WS 消息信封构建、user_msg 便捷函数、时间戳

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：覆盖 envelope / user_msg / now_ts
"""
import shared.protocol as p


def test_envelope_full_fields():
    env = p.envelope("user_msg", {"text": "hi"}, object_id="o1", msg_id="m1", ts=42)
    assert env == {
        "type": "user_msg", "object_id": "o1", "msg_id": "m1",
        "payload": {"text": "hi"}, "ts": 42,
    }


def test_envelope_auto_ts_when_zero():
    env = p.envelope("x", {})
    assert isinstance(env["ts"], int) and env["ts"] > 0


def test_user_msg_helper():
    msg = p.user_msg("hello", object_id="o2")
    assert msg["type"] == p.TYPE_USER_MSG
    assert msg["payload"] == {"text": "hello"}
    assert msg["object_id"] == "o2"


def test_user_msg_default_object():
    msg = p.user_msg("hi")
    assert msg["object_id"] == "default"


def test_now_ts_non_decreasing():
    assert p.now_ts() <= p.now_ts()
