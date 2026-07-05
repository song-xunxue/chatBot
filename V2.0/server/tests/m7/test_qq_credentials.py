"""
rest_system QQ 凭证管理单测(QQ 凭证面板化):
GET 掩码(不返 secret 明文)/ PUT 写 Redis + 清 token + settings 更新 + 重建客户端 / 必填校验 /
_apply_credential_overrides merge(Redis 覆盖 env)。

作者: 李文煜
日期: 2026-07-05
"""
import json
import time

import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_system import (_apply_credential_overrides, _K_QQ_APP_ID, _K_QQ_APP_SECRET,
                              router as system_router)
from core.config import settings
from qq.auth import _TOKEN_KEY

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    monkeypatch.setattr(settings, "qq_app_id", "appid-old")
    monkeypatch.setattr(settings, "qq_app_secret", "secret-old")
    app = FastAPI()
    app.include_router(system_router)
    return app


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _noop(*a, **k):
    pass


async def test_get_masks_secret(monkeypatch, fake_redis):
    """GET:app_id 明文(机器人标识,非敏感);secret 仅返 has_secret(不泄露,防冒充调 QQ API)"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/system/qq-credentials", headers=_H)
        assert r.status_code == 200
        d = r.json()
        assert set(d.keys()) == {"app_id", "has_secret"}   # 无 secret 字段
        assert d["app_id"] == "appid-old"
        assert d["has_secret"] is True


async def test_put_persists_redis_clears_token_updates_settings(monkeypatch, fake_redis):
    """PUT:写 Redis 两键 + 删旧 access_token 缓存 + settings 更新"""
    app = _wire(monkeypatch, fake_redis)
    await fake_redis.set(_TOKEN_KEY, json.dumps({"value": "old-tok", "expires_at": time.time() + 9999}))
    # mock httpx 客户端重建(避免真连)
    monkeypatch.setattr("qq.auth.close_client", _noop)
    monkeypatch.setattr("qq.auth.init_client", _noop)
    monkeypatch.setattr("qq.api_client.close_client", _noop)
    monkeypatch.setattr("qq.api_client.init_client", _noop)
    async with await _ac(app) as ac:
        r = await ac.put("/api/v1/system/qq-credentials",
                         json={"app_id": "appid-new", "app_secret": "secret-new"}, headers=_H)
        assert r.status_code == 200
    assert await fake_redis.get(_K_QQ_APP_ID) == "appid-new"
    assert await fake_redis.get(_K_QQ_APP_SECRET) == "secret-new"
    assert await fake_redis.get(_TOKEN_KEY) is None              # 旧 token 清,强制新 secret 换
    assert settings.qq_app_id == "appid-new"
    assert settings.qq_app_secret == "secret-new"


async def test_put_requires_both_fields(monkeypatch, fake_redis):
    """app_id 和 app_secret 均必填"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.put("/api/v1/system/qq-credentials",
                             json={"app_id": "x"}, headers=_H)).status_code == 400
        assert (await ac.put("/api/v1/system/qq-credentials",
                             json={"app_id": "", "app_secret": "y"}, headers=_H)).status_code == 400


async def test_apply_overrides_merges_redis(monkeypatch, fake_redis):
    """_apply_credential_overrides:Redis 有值则覆盖 settings(模拟 reload/启动灌入);无值保留 env"""
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    monkeypatch.setattr(settings, "qq_app_id", "from-env")
    monkeypatch.setattr(settings, "qq_app_secret", "secret-env")
    await fake_redis.set(_K_QQ_APP_ID, "from-redis")   # 仅 app_id 有 Redis 覆盖
    await _apply_credential_overrides(settings)
    assert settings.qq_app_id == "from-redis"           # Redis 覆盖 env
    assert settings.qq_app_secret == "secret-env"       # Redis 无值,保留 env
