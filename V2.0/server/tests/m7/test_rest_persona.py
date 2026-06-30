"""
rest_persona REST 单测(M7):鉴权 / CRUD / 模型绑定 / 导入(嵌套形态)/ 导出 / 快照回滚。
独立 app(仅挂 persona_router)。

作者: 李文煜
日期: 2026-06-30
"""
import json

import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_persona import router as persona_router
from core.config import settings
from persona import store as persona_store
from persona.models import PersonaCard

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(persona_router)
    return app


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_persona_auth_required(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/persona")).status_code == 401


async def test_persona_crud(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/persona", json={"id": "p1", "name": "A"}, headers=_H)).status_code == 200
        assert len((await ac.get("/api/v1/persona", headers=_H)).json()) == 1
        assert (await ac.get("/api/v1/persona/p1", headers=_H)).json()["name"] == "A"
        assert (await ac.put("/api/v1/persona/p1", json={"name": "B"}, headers=_H)).json()["name"] == "B"
        assert (await ac.delete("/api/v1/persona/p1", headers=_H)).json()["deleted"] is True
        assert (await ac.get("/api/v1/persona/p1", headers=_H)).status_code == 404


async def test_create_missing_id_400(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/persona", json={"name": "X"}, headers=_H)).status_code == 400


async def test_model_bind(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await persona_store.set_persona(fake_redis, PersonaCard(id="p1"))
    async with await _ac(app) as ac:
        r = await ac.put("/api/v1/persona/p1/model",
                         json={"provider": "deepseek", "model": "chat"}, headers=_H)
        assert r.status_code == 200
        assert r.json()["model"]["provider"] == "deepseek"
    card = await persona_store.get_persona(fake_redis, "p1")
    assert card.model.provider == "deepseek"


async def test_import_and_export(monkeypatch, fake_redis):
    """导入嵌套形态 persona_*.json → 导出"""
    app = _wire(monkeypatch, fake_redis)
    data = {"spec": "chara_card_v2", "data": {
        "name": "导入", "description": "d",
        "prompts": {"pid_x": {"name": "导入", "data": {"name": "导入", "description": "d"}}}}}
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/persona/import",
                          files={"file": ("p.json", json.dumps(data).encode("utf-8"), "application/json")},
                          headers=_H)
        assert r.status_code == 200
        pid = r.json()["id"]
        assert r.json()["name"] == "导入"
        r2 = await ac.get(f"/api/v1/persona/{pid}/export", headers=_H)
        assert r2.status_code == 200
        assert r2.json()["data"]["name"] == "导入"


async def test_snapshot_and_rollback(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    await persona_store.set_persona(fake_redis, PersonaCard(id="p1", name="原"))
    async with await _ac(app) as ac:
        # 快照 v1(原)
        v1 = (await ac.post("/api/v1/persona/p1/snapshot", headers=_H)).json()["version_no"]
        # 改名
        await ac.put("/api/v1/persona/p1", json={"name": "改"}, headers=_H)
        assert (await persona_store.get_persona(fake_redis, "p1")).name == "改"
        # 回滚到 v1
        r = await ac.post("/api/v1/persona/p1/rollback", json={"version_no": v1}, headers=_H)
        assert r.status_code == 200
        assert r.json()["name"] == "原"


async def test_snapshot_404(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/persona/nope/snapshot", headers=_H)).status_code == 404
