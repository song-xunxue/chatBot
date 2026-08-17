"""
测试公共夹具(V3.0,2026-08-17 精简版)
提供:sys.path 兜底、fakeredis 注入、LLM key 清空、统一 fake_adapter(出站替身)。
原 QQ 官方栈夹具(secret/签名/MockTransport)已随官方栈删除——V3.0 纯 OneBot,
出站 mock 统一在 adapter 层(注入 adapter._current 单例)。

作者: 李文煜
日期: 2026-06-25

2026-08-17
变更说明：
  1. V3.0 精简:删 qq 官方夹具(_qq_secret/auth_client/api_client/qq_http/make_signature/now_ts);
     新增 fake_adapter(全测试统一出站替身,记录 send_text/send_voice 调用)
"""
import sys
from pathlib import Path

# 兜底 sys.path:让 server/app(core/adapter/storage)可被同级导入
_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parent / "app"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
import fakeredis

import storage.redis_client as redis_client
from core.config import settings


@pytest.fixture(autouse=True)
def _reset_adapter_singleton():
    """自动重置 adapter 单例(每个测试独立,防跨测试泄漏;fake_adapter 注入也在其上)"""
    import adapter as adapter_mod
    adapter_mod.reset_adapter()
    yield
    adapter_mod.reset_adapter()


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
    """自动关闭 tool-loop(M5):m1-m4 测试不经 tool-loop(走 stream_chat);m5 测试显式 monkeypatch 开。"""
    monkeypatch.setattr(settings, "tool_loop_enable", False)


@pytest.fixture
def fake_redis():
    """注入 fakeredis 单例到 storage.redis_client._redis(缓存走内存假 Redis)"""
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    redis_client._redis = fake
    yield fake
    redis_client._redis = None


class _RecordingAdapter:
    """统一出站替身:记录 send_text/send_voice 调用;fail_on 控制抛异常(测降级分支)。
    monkeypatch 注入 adapter._current(get_current_adapter 见非 None 直接返回)。"""

    def __init__(self):
        self.sent: list[tuple] = []     # (kind, oid, content, msg_id, msg_seq, extra)
        self.fail_on: str | None = None  # "text"/"voice"/"all" 时对应调用抛 RuntimeError

    def _maybe_raise(self, kind: str) -> None:
        if self.fail_on in (kind, "all"):
            raise RuntimeError(f"fake_adapter {kind} 下发失败(测试注入)")

    async def send_text(self, oid, content, *, msg_id="", msg_seq=1, human_authored=False):
        self._maybe_raise("text")
        self.sent.append(("text", oid, content, msg_id, msg_seq, human_authored))
        return {"delivered": True, "mode": "fake_text"}

    async def send_voice(self, oid, silk_bytes, *, msg_id="", msg_seq=1, content=""):
        self._maybe_raise("voice")
        self.sent.append(("voice", oid, silk_bytes, msg_id, msg_seq, content))
        return {"delivered": True, "mode": "fake_voice"}

    async def init(self):
        pass

    async def close(self):
        pass


@pytest.fixture
def fake_adapter(monkeypatch):
    """注入出站替身到 adapter 单例(测试内业务代码经 get_current_adapter 全走替身)"""
    import adapter as adapter_mod
    fa = _RecordingAdapter()
    monkeypatch.setattr(adapter_mod, "_current", fa)
    yield fa
