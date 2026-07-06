"""
rest_persona REST 单测(M7):鉴权 / 取·改 / 模型绑定 / 导出 / 快照回滚。
单人设简化(2026-07-04):create/delete/import 端点已删,改用 store 层种数据测读改/导出。

作者: 李文煜
日期: 2026-06-30
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_persona import router as persona_router
from core.config import settings
from persona import store as persona_store
from persona.models import PersonaCard, Profile

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


async def test_persona_get_update(monkeypatch, fake_redis):
    """list/get/update(用 store 种;create 端点单人设简化已删)"""
    app = _wire(monkeypatch, fake_redis)
    await persona_store.set_persona(fake_redis, PersonaCard(id="p1", name="A"))
    async with await _ac(app) as ac:
        assert len((await ac.get("/api/v1/persona", headers=_H)).json()) == 1
        assert (await ac.get("/api/v1/persona/p1", headers=_H)).json()["name"] == "A"
        assert (await ac.put("/api/v1/persona/p1", json={"name": "B"}, headers=_H)).json()["name"] == "B"


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


async def test_export(monkeypatch, fake_redis):
    """导出(用 store 种;import 端点单人设简化已删)"""
    app = _wire(monkeypatch, fake_redis)
    await persona_store.set_persona(fake_redis, PersonaCard(id="p1", name="导出", description="d"))
    async with await _ac(app) as ac:
        r2 = await ac.get("/api/v1/persona/p1/export", headers=_H)
        assert r2.status_code == 200
        assert r2.json()["data"]["name"] == "导出"


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


async def test_update_nested_profile_field_level_merge(monkeypatch, fake_redis):
    """B-5a:update_persona 对 profile 嵌套字段级合并,只传 speech_style 不丢 age/gender 等其他字段。
    背景:面板暴露 speech_style/catchphrase 编辑,旧逻辑 merged.update 整体替换 profile 会丢字段。"""
    app = _wire(monkeypatch, fake_redis)
    await persona_store.set_persona(fake_redis, PersonaCard(
        id="p1", name="A", profile=Profile(age="20岁", gender="女", speech_style="温柔"),
    ))
    async with await _ac(app) as ac:
        r = await ac.put("/api/v1/persona/p1",
                         json={"profile": {"speech_style": "简短直接"}}, headers=_H)
        assert r.status_code == 200
    card = await persona_store.get_persona(fake_redis, "p1")
    assert card.profile.speech_style == "简短直接"   # 新值
    assert card.profile.age == "20岁"               # 未传字段保留(字段级合并)
    assert card.profile.gender == "女"              # 未传字段保留


async def test_update_top_level_personality_scenario(monkeypatch, fake_redis):
    """B-5a:顶层字段 personality/scenario 直接覆盖(面板暴露这些字段编辑)"""
    app = _wire(monkeypatch, fake_redis)
    await persona_store.set_persona(fake_redis, PersonaCard(id="p1", personality="原性格"))
    async with await _ac(app) as ac:
        await ac.put("/api/v1/persona/p1",
                     json={"personality": "新性格", "scenario": "教室"}, headers=_H)
    card = await persona_store.get_persona(fake_redis, "p1")
    assert card.personality == "新性格"
    assert card.scenario == "教室"
