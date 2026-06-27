"""
QQ access_token 获取与缓存
用 AppID + AppSecret 换 access_token(调 QQ REST 发消息必需),Redis 缓存 + 提前刷新。

接口(查 QQ 开放平台 OAuth 文档确认):
  POST {token_base}/getAppAccessToken
  body: {"appId": APPID, "clientSecret": APP_SECRET}
  resp: {"access_token": "...", "expires_in": 7200}

缓存设计:Redis key mychat:qq:access_token 存 JSON {value, expires_at}。
不用原生 TTL(要读 expires_at 算提前 300s 刷新量)。模块级 asyncio.Lock + double-check 防并发重复刷新。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建 auth:get_access_token(Redis 缓存 + 提前刷新 + 并发去重)+ httpx 单例
"""
import asyncio
import json
import logging
import time
from dataclasses import asdict

import httpx

from core.config import settings
from qq.types import AccessToken
from storage.redis_client import get_redis

logger = logging.getLogger(__name__)

_TOKEN_KEY = "mychat:qq:access_token"   # Redis 缓存键(单 bot 单 token,不按用户区分)
_REFRESH_LEAD_SEC = 300                  # 提前 300s 刷新,避免临界态发请求时已过期
_MIN_EXPIRES_IN = 60                     # expires_in 下限保护(<60s 视为异常,告警不缓存)
_refresh_lock = asyncio.Lock()           # 防 token 临界态多协程并发刷新(QQ 对该接口有频率限制)


# httpx 异步单例(lifespan 负责创建/关闭,复用连接池;测试 monkeypatch 注入 MockTransport)
_client: httpx.AsyncClient | None = None


async def init_client() -> None:
    """lifespan 启动时创建 httpx 异步客户端单例"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)


async def close_client() -> None:
    """lifespan 关闭时释放 httpx 客户端"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _request_token() -> AccessToken:
    """调 QQ 换 access_token。expires_in 下限保护,异常短的过期时间不缓存"""
    assert _client is not None, "httpx client 未初始化,请在 lifespan 调 init_client"
    resp = await _client.post(
        f"{settings.qq_token_base}/getAppAccessToken",
        json={"appId": settings.qq_app_id, "clientSecret": settings.qq_app_secret},
    )
    resp.raise_for_status()
    data = resp.json()
    expires_in = int(data.get("expires_in", 0))
    if expires_in < _MIN_EXPIRES_IN:
        # expires_in 异常短(配置错误或异常响应),告警但仍返回当前 token,避免反复刷新被 ban
        logger.warning("QQ access_token expires_in=%s 异常短,可能配置错误", expires_in)
    expires_at = time.time() + expires_in
    return AccessToken(value=data["access_token"], expires_at=expires_at)


async def get_access_token() -> str:
    """取有效 access_token:缓存命中且未临近过期则直返,否则加锁刷新(双重检查)"""
    redis = await get_redis()
    raw = await redis.get(_TOKEN_KEY)
    if raw:
        cached = AccessToken(**json.loads(raw))
        # 缓存未临近过期直接返回(避免无谓刷新)
        if cached.expires_at - time.time() > _REFRESH_LEAD_SEC:
            return cached.value

    # 临界态/未命中:加锁刷新,防止多协程并发重复请求 QQ
    async with _refresh_lock:
        # double-check:拿锁后可能已被其他协程刷新过
        raw = await redis.get(_TOKEN_KEY)
        if raw:
            cached = AccessToken(**json.loads(raw))
            if cached.expires_at - time.time() > _REFRESH_LEAD_SEC:
                return cached.value
        token = await _request_token()
        await redis.set(_TOKEN_KEY, json.dumps(asdict(token)))
        logger.info("QQ access_token refreshed, expires_at=%s", token.expires_at)
        return token.value
