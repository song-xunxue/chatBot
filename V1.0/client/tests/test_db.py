"""
ChatStore 测试：消息追加/读取、上限清理、outbox 入队/补发。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 覆盖 ChatStore：messages CRUD + 上限清理 + outbox
"""


def test_append_and_get_messages(store):
    store.append_message("o1", "user", "你好", ts=1)
    store.append_message("o1", "assistant", "你好呀", ts=2, rich={"audio": ["x"]})
    msgs = store.get_messages("o1")
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].rich == {"audio": ["x"]}
    assert msgs[0].text == "你好"


def test_message_limit_evicts_oldest(store):
    """上限 5：插 7 条，仅保留最近 5 条"""
    for i in range(7):
        store.append_message("o1", "user", f"m{i}", ts=i)
    msgs = store.get_messages("o1")
    assert len(msgs) == 5
    assert msgs[0].text == "m2"           # 最旧 m0/m1 被清理
    assert msgs[-1].text == "m6"


def test_limit_isolated_per_object(store):
    """上限按对象独立计数"""
    for i in range(5):
        store.append_message("o1", "user", f"a{i}", ts=i)
    store.append_message("o2", "user", "b", ts=1)
    assert len(store.get_messages("o1")) == 5
    assert len(store.get_messages("o2")) == 1


def test_outbox_enqueue_pending_mark(store):
    store.enqueue_outbox("o1", "离线消息1", ts=1)
    store.enqueue_outbox("o1", "离线消息2", ts=2)
    pending = store.pending_outbox("o1")
    assert [r["text"] for r in pending] == ["离线消息1", "离线消息2"]
    store.mark_outbox_sent(pending[0]["id"])
    pending2 = store.pending_outbox("o1")
    assert [r["text"] for r in pending2] == ["离线消息2"]
