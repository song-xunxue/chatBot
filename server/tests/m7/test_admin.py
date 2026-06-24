"""
rest_admin 测试：models / history / persona_evolve 提案列表+忽略、鉴权。
播种经 redis_client._redis（与 client fixture 同一 fakeredis，避免双实例竞态）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M7 覆盖 rest_admin：models/history/proposals
"""
import asyncio
import json

import storage.redis_client as rc
from core.config import settings

HEADERS = {"X-Access-Token": settings.access_token}


def test_models(client):
    r = client.get("/api/v1/models", headers=HEADERS)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["providers"]]
    assert names == ["glm", "deepseek", "siliconflow"]
    for p in r.json()["providers"]:
        assert "configured" in p and "available" in p


def test_history_empty(client):
    r = client.get("/api/v1/history/o-none", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["object_id"] == "o-none"
    assert isinstance(body["messages"], list)


def test_history_with_messages(client):
    """直接写几条历史再查（用 client 的同一 redis）"""
    from storage import chat_store

    async def seed():
        await chat_store.append_message(rc._redis, "o-h", "user", "hi", ts=1)
        await chat_store.append_message(rc._redis, "o-h", "assistant", "hey", ts=2)

    asyncio.run(seed())
    r = client.get("/api/v1/history/o-h", headers=HEADERS)
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_proposals_list_and_dismiss(client):
    """造一条 persona_evolve 提案 → 列出 → 忽略"""

    async def seed():
        await rc._redis.set(
            "mychat:persona_evolve:proposal:o-p",
            json.dumps({"samples": [{"text": "bad", "reason": "out_of_character"}]}),
        )

    asyncio.run(seed())
    r = client.get("/api/v1/persona_evolve/proposals", headers=HEADERS)
    proposals = r.json()["proposals"]
    assert any(p["object_id"] == "o-p" for p in proposals)
    assert proposals[0]["samples"][0]["reason"] == "out_of_character"
    # 忽略
    r2 = client.delete("/api/v1/persona_evolve/proposals/o-p", headers=HEADERS)
    assert r2.json()["dismissed"] is True
    # 再列已无
    r3 = client.get("/api/v1/persona_evolve/proposals", headers=HEADERS)
    assert all(p["object_id"] != "o-p" for p in r3.json()["proposals"])


def test_auth_required(client):
    assert client.get("/api/v1/models").status_code == 401
