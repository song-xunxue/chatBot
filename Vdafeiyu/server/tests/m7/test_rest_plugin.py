"""
rest_plugin REST 单测(M7):鉴权 / 列表(原生+star 合并)/ 启用禁用 / 原生 reload /
.star reload / 404 / 503(未初始化)。用 mock PluginManager + mock StarLoader(独立 app 无 lifespan)。

日期: 2026-06-30

2026-10-26
变更说明:
  1. 补 PUT params 的 config_schema 服务端校验测试(审查修复:keep_days=0 可清光全部日记)
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_plugin import router as plugin_router
from core.config import settings

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(plugin_router)
    return app


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def _mock_manager(loaded=("p1",)):
    """轻量 mock PluginManager(覆盖 rest_plugin 用到的方法)"""
    mgr = MagicMock()
    mgr.list_loaded = MagicMock(return_value=list(loaded))
    mgr.get_manifest = MagicMock(return_value=None)        # 触发 _native_dict 走 {"name":..} 分支
    mgr.manifest_to_dict = MagicMock(return_value={"name": "p1", "display_name": "P1"})
    mgr.set_global_enabled = AsyncMock(return_value=None)
    mgr.get_global_enabled = AsyncMock(return_value=True)
    mgr.reload = AsyncMock(return_value=None)
    return mgr


def _mock_star(loaded=("s1",), reload_ok=True):
    star = MagicMock()
    star.list_loaded = MagicMock(return_value=list(loaded))
    star.reload_file = AsyncMock(return_value=reload_ok)
    return star


async def test_plugin_auth_required(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    monkeypatch.setattr("api.rest_plugin.get_plugin_manager", lambda: None)
    monkeypatch.setattr("api.rest_plugin.get_star_loader", lambda: None)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/plugin")).status_code == 401


async def test_list_plugins_merged(monkeypatch, fake_redis):
    """原生 + .star 合并列表"""
    app = _wire(monkeypatch, fake_redis)
    monkeypatch.setattr("api.rest_plugin.get_plugin_manager", lambda: _mock_manager(["p1"]))
    monkeypatch.setattr("api.rest_plugin.get_star_loader", lambda: _mock_star(["s1"]))
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/plugin", headers=_H)
        m = {p["name"]: p for p in r.json()}
        assert m["p1"]["type"] == "native"
        assert m["s1"]["type"] == "star"


async def test_enable_disable_calls_manager(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    mgr = _mock_manager(["p1"])
    monkeypatch.setattr("api.rest_plugin.get_plugin_manager", lambda: mgr)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/plugin/p1/enable", headers=_H)).status_code == 200
        assert (await ac.post("/api/v1/plugin/p1/disable", headers=_H)).status_code == 200
    mgr.set_global_enabled.assert_any_call("p1", True)
    mgr.set_global_enabled.assert_any_call("p1", False)


async def test_native_reload(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    mgr = _mock_manager(["p1"])
    monkeypatch.setattr("api.rest_plugin.get_plugin_manager", lambda: mgr)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/plugin/p1/reload", headers=_H)
        assert r.status_code == 200
        assert r.json()["type"] == "native"
    mgr.reload.assert_awaited_with("p1")


async def test_star_reload_and_not_found(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    monkeypatch.setattr("api.rest_plugin.get_plugin_manager", lambda: _mock_manager([]))
    # s1 reload 成功
    star_ok = _mock_star(["s1"], reload_ok=True)
    monkeypatch.setattr("api.rest_plugin.get_star_loader", lambda: star_ok)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/plugin/star/s1/reload", headers=_H)
        assert r.status_code == 200
    star_ok.reload_file.assert_awaited_with("s1")
    # reload_file 返回 False → 404
    star_fail = _mock_star(["s1"], reload_ok=False)
    monkeypatch.setattr("api.rest_plugin.get_star_loader", lambda: star_fail)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/plugin/star/nope/reload", headers=_H)).status_code == 404


async def test_star_reload_not_initialized_503(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    monkeypatch.setattr("api.rest_plugin.get_star_loader", lambda: None)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/plugin/star/s1/reload", headers=_H)).status_code == 503


async def test_enable_not_found_404(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    monkeypatch.setattr("api.rest_plugin.get_plugin_manager", lambda: _mock_manager([]))
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/plugin/nope/enable", headers=_H)).status_code == 404


def _mock_manager_with_schema(schema: dict):
    """带 config_schema 的 manager mock(PUT params 校验用)"""
    mgr = _mock_manager(["p1"])
    mgr.get_manifest = MagicMock(return_value=SimpleNamespace(config_schema=schema))
    mgr.set_object_config = AsyncMock(return_value=None)
    return mgr


async def test_set_params_schema_validation(monkeypatch, fake_redis):
    """PUT params 按 config_schema 校验(审查修复):类型错/越 min-max → 400
    (keep_days=0 会一次清理删光全部日记,须拦);None(回退默认)与未声明键放行"""
    app = _wire(monkeypatch, fake_redis)
    schema = {
        "keep_days": {"type": "number", "min": 7, "max": 365},
        "auto_on": {"type": "bool"},
        "label": {"type": "string"},
    }
    mgr = _mock_manager_with_schema(schema)
    monkeypatch.setattr("api.rest_plugin.get_plugin_manager", lambda: mgr)
    monkeypatch.setattr("api.rest_plugin.get_star_loader", lambda: None)
    async with await _ac(app) as ac:
        base = "/api/v1/plugin/p1/params?object_id=10001"
        # 违例矩阵:低于 min / 超过 max / 数值收到串 / bool 收到串 / string 收到数
        assert (await ac.put(base, headers=_H, json={"keep_days": 0})).status_code == 400
        assert (await ac.put(base, headers=_H, json={"keep_days": 400})).status_code == 400
        assert (await ac.put(base, headers=_H, json={"keep_days": "abc"})).status_code == 400
        assert (await ac.put(base, headers=_H, json={"auto_on": "yes"})).status_code == 400
        assert (await ac.put(base, headers=_H, json={"label": 3})).status_code == 400
        # 放行:合法值 + 未声明键(兼容存量) + None(回退默认)
        assert (await ac.put(base, headers=_H, json={"keep_days": 30, "unknown_key": "x"})).status_code == 200
        assert (await ac.put(base, headers=_H, json={"keep_days": None})).status_code == 200
    mgr.set_object_config.assert_awaited()
