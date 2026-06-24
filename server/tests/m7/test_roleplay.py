"""
代人聊天 A 面板模拟训练测试（V1.1 M11）
验证 roleplay 正样本录/列/改/删、物理隔离（不污染真实历史）、object_id 绑定校验。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. V1.1 M11 覆盖 rest_roleplay + chat_store roleplay 函数
"""
from core.config import settings

HEADERS = {"X-Access-Token": settings.access_token}


def test_roleplay_training(client):
    """录一对 → 列两条 → 改 → 删（记负样本）"""
    oid = "rpobj"
    client.post(f"/api/v1/persona/default/bind/{oid}", headers=HEADERS)   # 先绑定人设
    r = client.post(f"/api/v1/roleplay/{oid}/messages",
                    json={"user_text": "你好", "assistant_text": "嗨~"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    msgs = client.get(f"/api/v1/roleplay/{oid}/messages", headers=HEADERS).json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user" and msgs[0]["content"] == "你好"
    assert msgs[1]["role"] == "assistant" and msgs[1]["content"] == "嗨~"
    # 改写
    mid = msgs[0]["mid"]
    client.put(f"/api/v1/roleplay/{oid}/messages/{mid}", json={"content": "你好啊"}, headers=HEADERS)
    msgs = client.get(f"/api/v1/roleplay/{oid}/messages", headers=HEADERS).json()["messages"]
    assert msgs[0]["content"] == "你好啊"
    # 删除 → 剩 1 条
    client.delete(f"/api/v1/roleplay/{oid}/messages/{mid}", headers=HEADERS)
    msgs = client.get(f"/api/v1/roleplay/{oid}/messages", headers=HEADERS).json()["messages"]
    assert len(msgs) == 1


def test_roleplay_isolation(client):
    """关键正确性：roleplay 正样本不进入真实聊天历史（get_history 取不到）"""
    oid = "isoobj"
    client.post(f"/api/v1/persona/default/bind/{oid}", headers=HEADERS)
    client.post(f"/api/v1/roleplay/{oid}/messages",
                json={"user_text": "u", "assistant_text": "a"}, headers=HEADERS)
    # rest_admin /history 读 chat_store.get_history（mychat:chat:{oid}），不含 roleplay
    hist = client.get(f"/api/v1/history/{oid}", headers=HEADERS).json()["messages"]
    assert hist == []


def test_roleplay_unbound_object_rejected(client):
    """未绑定人设的 object_id 拒绝录入（防孤儿 chat List）"""
    r = client.post("/api/v1/roleplay/ghostobj/messages",
                    json={"user_text": "u", "assistant_text": "a"}, headers=HEADERS)
    assert r.status_code == 400


def test_roleplay_missing_fields_rejected(client):
    """user_text/assistant_text 缺一不可"""
    oid = "mfobj"
    client.post(f"/api/v1/persona/default/bind/{oid}", headers=HEADERS)
    r = client.post(f"/api/v1/roleplay/{oid}/messages",
                    json={"user_text": "u"}, headers=HEADERS)
    assert r.status_code == 400


def test_roleplay_update_delete_missing_mid(client):
    """改/删不存在的 mid → 404"""
    oid = "missobj"
    client.post(f"/api/v1/persona/default/bind/{oid}", headers=HEADERS)
    assert client.put(f"/api/v1/roleplay/{oid}/messages/nope",
                      json={"content": "x"}, headers=HEADERS).status_code == 404
    assert client.delete(f"/api/v1/roleplay/{oid}/messages/nope", headers=HEADERS).status_code == 404
