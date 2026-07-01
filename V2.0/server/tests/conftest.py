"""
测试公共夹具(M1)
提供:sys.path 兜底、fakeredis 注入、httpx MockTransport 注入、QQ secret 配置、签名生成器。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建 conftest:fakeredis + httpx MockTransport + QQ 凭证 + 测试签名生成
"""
import sys
import time
from pathlib import Path

# 兜底 sys.path:让 server/app(core/qq/storage)可被同级导入
_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parent / "app"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import httpx
import pytest
import fakeredis
from nacl.signing import SigningKey

import storage.redis_client as redis_client
from core.config import settings
import qq.auth as qq_auth
import qq.api_client as qq_api

# 测试用固定 AppSecret(既换 token 又作 Ed25519 验签派生源,用于自签自验闭环 + 金标准)
TEST_APP_SECRET = "test-app-secret-1234567890abcdef"


@pytest.fixture(autouse=True)
def _qq_secret(monkeypatch):
    """自动注入测试用 QQ 凭证 + 重置 httpx 单例(每个测试独立)"""
    monkeypatch.setattr(settings, "qq_app_id", "test-appid")
    monkeypatch.setattr(settings, "qq_app_secret", TEST_APP_SECRET)  # AppSecret 既换 token 又验签(测试用固定值)
    # 重置 httpx 单例,确保下个测试用新 MockTransport
    qq_auth._client = None
    qq_api._client = None
    yield
    qq_auth._client = None
    qq_api._client = None


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """自动清空 LLM api key,使 available_providers() 返回 [](pytest 全程不真调 LLM)。
    避免评分/反推/Memory 编码等 LLM 调用在测试中真烧 API;真实 LLM 验证走 scripts/real_llm_check.py。
    同时把 provider 选择项重置为默认 glm(隔离本地 .env 的 CHAT_PROVIDER/REVERSE_INFER_PROVIDER 覆盖,
    使测试不依赖部署环境配置,固定按 glm mock 路径跑)。"""
    monkeypatch.setattr(settings, "glm_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
    monkeypatch.setattr(settings, "chat_provider", "glm")
    monkeypatch.setattr(settings, "reverse_infer_provider", "glm")
    monkeypatch.setattr(settings, "score_provider", "")
    monkeypatch.setattr(settings, "memory_summary_provider", "")


@pytest.fixture(autouse=True)
def _disable_tool_loop(monkeypatch):
    """自动关闭 tool-loop(M5):m1-m4 测试不经 tool-loop(走 stream_chat);m5 测试显式 monkeypatch 开。
    避免 lifespan 注册的自研工具污染全局 registry 导致 m2/m3/m4 的 mock provider 走 tool-loop 崩。"""
    monkeypatch.setattr(settings, "tool_loop_enable", False)


@pytest.fixture
def fake_redis():
    """注入 fakeredis 单例到 storage.redis_client._redis(token 缓存走内存假 Redis)"""
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    redis_client._redis = fake
    yield fake
    redis_client._redis = None


def _make_mock_client():
    """构造带 MockTransport 的 httpx 客户端:getAppAccessToken 返 token-xyz,其余返发消息响应"""
    captured = {"requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["requests"].append(request)
        if "getAppAccessToken" in str(request.url):
            return httpx.Response(200, json={"access_token": "token-xyz", "expires_in": 7200})
        return httpx.Response(200, json={"id": "MSG-001", "timestamp": 1700000000})

    captured["client"] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return captured


@pytest.fixture
def auth_client():
    """仅给 qq.auth 注入 MockTransport(测 token 缓存/刷新)"""
    captured = _make_mock_client()
    qq_auth._client = captured["client"]
    return captured


@pytest.fixture
def api_client():
    """仅给 qq.api_client 注入 MockTransport(测发消息)"""
    captured = _make_mock_client()
    qq_api._client = captured["client"]
    return captured


@pytest.fixture
def qq_http():
    """同时给 qq.auth + qq.api_client 注入共享 MockTransport(echo 集成测试用,token+发消息同 handler)"""
    captured = _make_mock_client()
    qq_auth._client = captured["client"]
    qq_api._client = captured["client"]
    return captured


@pytest.fixture
def make_signature():
    """返回签名生成函数:用 TEST_BOT_SECRET 派生私钥,对 timestamp+body 签名(自签自验闭环)"""

    def _sign(timestamp: str, body: bytes, secret: str = TEST_APP_SECRET) -> str:
        from qq.webhook import _derive_seed
        sk = SigningKey(_derive_seed(secret))
        return sk.sign(timestamp.encode("utf-8") + body).signature.hex()

    return _sign


@pytest.fixture
def now_ts():
    """当前秒级时间戳字符串(验签防重放用,保证不超期)"""
    return str(int(time.time()))
