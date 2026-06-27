"""
access_token 缓存与刷新测试(fakeredis + httpx MockTransport)

作者: 李文煜
日期: 2026-06-25
"""
import json
import time

from qq.auth import get_access_token, _TOKEN_KEY


async def test_token_cached_skips_request(fake_redis, auth_client):
    """缓存命中且未临近过期 → 直接返回缓存,不请求 QQ"""
    await fake_redis.set(_TOKEN_KEY, json.dumps({"value": "cached-tok", "expires_at": time.time() + 9999}))
    token = await get_access_token()
    assert token == "cached-tok"
    # 不应触发任何 QQ 请求
    assert not [r for r in auth_client["requests"] if "getAppAccessToken" in str(r.url)]


async def test_token_refresh_when_expired(fake_redis, auth_client):
    """缓存已过期 → 请求 QQ 刷新,返回新 token 并写入缓存"""
    await fake_redis.set(_TOKEN_KEY, json.dumps({"value": "old-tok", "expires_at": time.time() - 1}))
    token = await get_access_token()
    assert token == "token-xyz"  # MockTransport 返回的
    assert [r for r in auth_client["requests"] if "getAppAccessToken" in str(r.url)]
    # 新 token 应写回缓存
    cached = json.loads(await fake_redis.get(_TOKEN_KEY))
    assert cached["value"] == "token-xyz"


async def test_token_first_call_requests(fake_redis, auth_client):
    """无缓存(首次)→ 请求 QQ"""
    token = await get_access_token()
    assert token == "token-xyz"
    token_reqs = [r for r in auth_client["requests"] if "getAppAccessToken" in str(r.url)]
    assert len(token_reqs) == 1
    # 请求体含 appId + clientSecret
    body = json.loads(token_reqs[0].content)
    assert body["appId"] == "test-appid"
    from core.config import settings
    assert body["clientSecret"] == settings.qq_app_secret


async def test_token_request_uses_correct_endpoint(fake_redis, auth_client):
    """换 token 请求打到配置的 token_base/getAppAccessToken"""
    await get_access_token()
    url = str([r for r in auth_client["requests"] if "getAppAccessToken" in str(r.url)][0].url)
    assert url.startswith("https://bots.qq.com/app/getAppAccessToken")
