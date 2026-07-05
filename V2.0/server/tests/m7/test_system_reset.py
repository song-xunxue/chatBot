"""
系统重置端点单测(2026-07-05):清空运行时数据,保留人设+配置白名单。
独立 app(仅挂 system_router)+ fakeredis 注入 + 白名单断言。

作者: 李文煜
日期: 2026-07-05
"""
import pytest
import httpx
import fakeredis
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_system import router as system_router
from core.config import settings

_H = {"X-Access-Token": "t-token"}


@pytest.fixture
def fake_redis():
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield fake


async def _aclient(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_reset_clears_runtime_keeps_persona(monkeypatch, fake_redis):
    """reset:清运行时(chat/mem/score/mood值/takeover),留人设+配置白名单"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    monkeypatch.setattr(settings, "access_token", "t-token")
    # 造数据:白名单(留)
    await fake_redis.set("mychat:persona:p1", "{}")
    await fake_redis.set("mychat:persona:_default_id", "p1")
    await fake_redis.set("mychat:persona_version:p1", "1")
    await fake_redis.set("mychat:obj:u1:persona", "p1")
    await fake_redis.set("mychat:config:qq_app_id", "APPID")
    await fake_redis.set("mychat:qq:access_token", "TOK")
    await fake_redis.set("mychat:mood:kinds", "[]")
    await fake_redis.set("mychat:mood:params", "{}")
    await fake_redis.set("mychat:plugin:hello:enabled", "1")
    # 造数据:运行时(清)
    await fake_redis.set("mychat:mood:u1", "0.5")
    await fake_redis.set("mychat:mood:u1:history", "[]")
    await fake_redis.set("mychat:chat:u1:blocks", "x")
    await fake_redis.set("mychat:msg:m1", "{}")
    await fake_redis.set("mychat:mem:u1:lt:1", "{}")
    await fake_redis.set("mychat:score:u1:positive", "[]")
    await fake_redis.set("mychat:takeover:u1:queue", "[]")
    await fake_redis.set("mychat:plugin_cfg:u1:hello", "{}")
    app = FastAPI()
    app.include_router(system_router)
    async with await _aclient(app) as ac:
        # 无确认词 → 400
        r0 = await ac.post("/api/v1/system/reset", json={}, headers=_H)
        assert r0.status_code == 400
        # 确认词错 → 400
        assert (await ac.post("/api/v1/system/reset", json={"confirm": "yes"}, headers=_H)).status_code == 400
        # 正确确认词 → 200
        r = await ac.post("/api/v1/system/reset", json={"confirm": "清空"}, headers=_H)
        data = r.json()
        assert data["deleted"] >= 7   # mood:u1/history/chat/msg/mem/score/takeover/plugin_cfg 至少
        assert data["kept"] >= 9      # 9 个白名单键
    # 白名单全保留
    for k in ["mychat:persona:p1", "mychat:persona:_default_id", "mychat:persona_version:p1",
              "mychat:obj:u1:persona", "mychat:config:qq_app_id", "mychat:qq:access_token",
              "mychat:mood:kinds", "mychat:mood:params", "mychat:plugin:hello:enabled"]:
        assert await fake_redis.exists(k), f"白名单键应保留: {k}"
    # 运行时全清
    for k in ["mychat:mood:u1", "mychat:mood:u1:history", "mychat:chat:u1:blocks", "mychat:msg:m1",
              "mychat:mem:u1:lt:1", "mychat:score:u1:positive", "mychat:takeover:u1:queue",
              "mychat:plugin_cfg:u1:hello"]:
        assert not await fake_redis.exists(k), f"运行时键应清空: {k}"
