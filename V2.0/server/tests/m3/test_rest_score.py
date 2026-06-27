"""
评分/反推 REST 接口单测(httpx.AsyncClient + ASGITransport,全 async 统一):
鉴权 / 取分(200+404)/ 手动改分 / 人设健康度 / 反推 dry_run+apply 两步契约 / 反推禁用 403。
用独立 app(仅挂 score_router,无 main lifespan)+ fakeredis 注入。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 创建 rest_score 单测(鉴权/取分/改分/健康度/反推两步契约/禁用 403)
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_score import router as score_router
from core.config import settings
from storage import chat_store
from mood import service as mood_service
from persona.models import PersonaCard
from persona import store as persona_store
from score import service as score_service

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    """注入 fakeredis + access_token,返回独立 app(仅挂 score_router)"""
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(score_router)
    return app


async def _aclient(app):
    """构造直连 ASGI 的异步客户端(不走网络,不触发 lifespan)"""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_auth_required(monkeypatch, fake_redis):
    """无 token / 错 token → 401"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        assert (await ac.get("/api/v1/chat/messages/m1/score")).status_code == 401
        r = await ac.get("/api/v1/chat/messages/m1/score", headers={"X-Access-Token": "wrong"})
        assert r.status_code == 401


async def test_get_score_200_and_404(monkeypatch, fake_redis, make_provider):
    """取分:命中 200 返回四元组;不存在 404"""
    app = _wire(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    monkeypatch.setattr("score.service.get_provider",
                        lambda n: make_provider('{"score": 90, "reason": "好"}'))
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="温柔回复")
    await score_service.score_reply(fake_redis, "u1", "温柔回复", PersonaCard(id="d"), mid, mood_value=0.5)

    async with await _aclient(app) as ac:
        r = await ac.get(f"/api/v1/chat/messages/{mid}/score", headers=_H)
        assert r.status_code == 200
        assert r.json()["score_base"] == 90
        # 不存在
        r2 = await ac.get("/api/v1/chat/messages/nope/score", headers=_H)
        assert r2.status_code == 404


async def test_manual_set_score(monkeypatch, fake_redis, make_provider):
    """PATCH 手动改分:覆盖 base,重算 score"""
    app = _wire(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    monkeypatch.setattr("score.service.get_provider",
                        lambda n: make_provider('{"score": 90, "reason": "好"}'))
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
    await score_service.score_reply(fake_redis, "u1", "x", PersonaCard(id="d"), mid, mood_value=0.5)

    async with await _aclient(app) as ac:
        r = await ac.patch(f"/api/v1/chat/messages/{mid}/score",
                           json={"score_base": 50}, headers=_H)
        assert r.status_code == 200
        assert r.json()["score_base"] == 50
        # 缺字段 400
        r2 = await ac.patch(f"/api/v1/chat/messages/{mid}/score", json={}, headers=_H)
        assert r2.status_code == 400


async def test_health(monkeypatch, fake_redis):
    """人设健康度:返回近 N 条均分 + 正/负/中计数"""
    app = _wire(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    for sc in (90, 70):
        mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
        await chat_store.set_score(fake_redis, mid, score_base=sc, mood_value=0.5, mood_bias=0)
    async with await _aclient(app) as ac:
        r = await ac.get("/api/v1/chat/u1/health", headers=_H)
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert body["positive"] == 1 and body["neutral"] == 1


async def test_reverse_infer_disabled_403(monkeypatch, fake_redis):
    """reverse_infer_enabled=False:dry_run/apply 返 403"""
    monkeypatch.setattr(settings, "reverse_infer_enabled", False)
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/score/reverse_infer/u1/dry_run", json={}, headers=_H)
        assert r.status_code == 403
        r2 = await ac.post("/api/v1/score/reverse_infer/u1/apply",
                           json={"confirm_token": "x"}, headers=_H)
        assert r2.status_code == 403


async def test_reverse_infer_dry_run_and_apply(monkeypatch, fake_redis, make_provider):
    """反推两步契约经 REST:dry_run 取 token → apply 合并"""
    app = _wire(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    card = PersonaCard(id="ptest", name="测试", creator_notes="核心")
    await persona_store.set_persona(fake_redis, card)
    await persona_store.bind_object_persona(fake_redis, "u1", "ptest")
    # 正样本
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    monkeypatch.setattr("score.service.get_provider",
                        lambda n: make_provider('{"score": 95, "reason": "好"}'))
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="温柔地回应")
    await score_service.score_reply(fake_redis, "u1", "温柔地回应", card, mid, mood_value=0.5)
    # 反推 provider
    monkeypatch.setattr("score.reverse_infer.get_provider",
                        lambda n: make_provider('{"personality":"温柔体贴"}'))

    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/score/reverse_infer/u1/dry_run", json={}, headers=_H)
        assert r.status_code == 200
        token = r.json()["confirm_token"]
        assert "personality" in r.json()["diff"]
        r2 = await ac.post("/api/v1/score/reverse_infer/u1/apply",
                           json={"confirm_token": token}, headers=_H)
        assert r2.status_code == 200 and r2.json()["merged"] is True
        applied = await persona_store.get_persona(fake_redis, "ptest")
        assert applied.personality == "温柔体贴"


async def test_reverse_infer_apply_no_token_400(monkeypatch, fake_redis):
    """apply 缺 token → 400(REST 层拦截)"""
    app = _wire(monkeypatch, fake_redis)
    async with await _aclient(app) as ac:
        r = await ac.post("/api/v1/score/reverse_infer/u1/apply", json={}, headers=_H)
        assert r.status_code == 400
