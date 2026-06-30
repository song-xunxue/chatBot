"""
rest_mood REST 单测(M7):鉴权 / 档位 CRUD(冲突 400)/ 全局参数读写(超范围 400)/
mood 读写 + 历史 / 评分试算。独立 app(仅挂 mood_router)。

作者: 李文煜
日期: 2026-06-30
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_mood import router as mood_router
from core.config import settings
from mood import service as mood_service

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(mood_router)
    return app


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_mood_auth_required(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/mood/kinds")).status_code == 401


async def test_kinds_list_and_upsert_conflict(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/mood/kinds", headers=_H)
        assert len(r.json()) == 5
        # upsert 与现有重叠 → 400
        bad = {"key": "bad", "label": "x", "mood_lo": 0.6, "mood_hi": 0.9,
               "kaomoji": "x", "score_bias": 0, "bias_noise": 3,
               "prompt_hint": "", "color": "#000", "sort": 9}
        assert (await ac.post("/api/v1/mood/kinds", json=bad, headers=_H)).status_code == 400
        # delete 删 sad(破坏覆盖)→ 400
        assert (await ac.delete("/api/v1/mood/kinds/sad", headers=_H)).status_code == 400


async def test_params_get_set_and_range(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/mood/params", headers=_H)
        assert r.json()["mood_step"] == settings.mood_step
        r2 = await ac.put("/api/v1/mood/params", json={"mood_step": 0.25}, headers=_H)
        assert r2.json()["mood_step"] == 0.25
        # 超范围 → 400
        assert (await ac.put("/api/v1/mood/params", json={"mood_step": 2}, headers=_H)).status_code == 400


async def test_mood_get_set_history(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    async with await _ac(app) as ac:
        rs = await ac.put("/api/v1/mood/u1", json={"mood": 0.8}, headers=_H)
        assert rs.json()["mood"] == 0.8
        r = await ac.get("/api/v1/mood/u1", headers=_H)
        assert r.json()["mood"] == 0.8
        assert r.json()["kind"]["key"] == "happy"
        rh = await ac.get("/api/v1/mood/u1/history", headers=_H)
        assert len(rh.json()) == 1


async def test_mood_calc(monkeypatch, fake_redis):
    """评分试算:mood=0.8(happy 档 bias≈6)→ score≈86(噪声多次采样均值)"""
    app = _wire(monkeypatch, fake_redis)
    await mood_service.seed_default_kinds(fake_redis)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/mood/u1/calc",
                          json={"score_base": 80, "mood": 0.8}, headers=_H)
        assert r.status_code == 200
        body = r.json()
        assert body["score_base"] == 80
        assert 4 <= body["mood_bias"] <= 8        # happy bias 均值≈6
        assert 83 <= body["score"] <= 89


async def test_mood_calc_missing_field(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/mood/u1/calc", json={}, headers=_H)).status_code == 400
