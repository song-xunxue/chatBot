"""
rest_system REST 单测(M7):鉴权 / config(provider 状态,不暴露 key)/ reload(in-place 刷新 settings)。
独立 app(仅挂 system_router);reload 的 QQ 客户端重建 mock 为 noop,Settings mock 验证 in-place 覆盖。

作者: 李文煜
日期: 2026-06-30
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_system import router as system_router
from core.config import settings, Settings

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(system_router)
    return app


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_system_auth_required(monkeypatch, fake_redis):
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/system/config")).status_code == 401


async def test_system_config(monkeypatch, fake_redis):
    """config 返回 provider 状态(configured 跟随 api_key),不暴露 key"""
    app = _wire(monkeypatch, fake_redis)
    monkeypatch.setattr(settings, "glm_api_key", "secret-key")
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/system/config", headers=_H)
        assert r.status_code == 200
        m = {p["name"]: p for p in r.json()["providers"]}
        assert m["glm"]["configured"] is True
        assert m["glm"]["available"] is True
        assert "secret-key" not in r.text      # 不暴露 key


async def test_system_reload_inplace(monkeypatch, fake_redis):
    """reload:重读 .env → in-place 覆盖 settings 单例 → 重建 QQ 客户端。
    用 mock Settings() 返回预设实例,验证 in-place setattr 生效。"""
    app = _wire(monkeypatch, fake_redis)
    fresh = Settings()
    monkeypatch.setattr(fresh, "cors_origins", "http://reloaded")   # 用无害字段验证
    monkeypatch.setattr("api.rest_system.Settings", lambda: fresh)
    # QQ 客户端重建 mock noop(reload 内 from qq import ...)
    async def _noop():
        return None
    monkeypatch.setattr("qq.auth.close_client", _noop)
    monkeypatch.setattr("qq.auth.init_client", _noop)
    monkeypatch.setattr("qq.api_client.close_client", _noop)
    monkeypatch.setattr("qq.api_client.init_client", _noop)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/system/reload", headers=_H)
        assert r.status_code == 200
        assert r.json()["reloaded"] is True
    # settings.cors_origins 被 in-place 覆盖为 fresh 的值
    assert settings.cors_origins == "http://reloaded"
