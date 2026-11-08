"""
BreezeBlue 云端 TTS provider 单测(2026-11-03)。
覆盖:文本截断(控费)/每日护栏(INCR 超限抛错,redis 不可用放行)/无 key 抛错/
get_tts 注册与无 key 降级 stub/合成参数(xi-api-key 头+output_format=mp3+返回二进制)。

日期: 2026-11-03
"""
import asyncio

import pytest
from core.config import settings
from modality.tts import BreezeBlueTTSProvider, get_tts


class _FakeRedis:
    """INCR 计数可编程的假 redis(护栏测试用)"""

    def __init__(self, fail=False, limit_hit_at=None):
        self.n = 0
        self.fail = fail               # True=模拟 redis 不可用(护栏应放行)
        self.limit_hit_at = limit_hit_at

    async def incr(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        self.n += 1
        return self.n

    async def expire(self, key, ttl):
        pass


@pytest.fixture
def _bb_on(monkeypatch):
    monkeypatch.setattr(settings, "breezeblue_api_key", "brz_test")
    monkeypatch.setattr(settings, "breezeblue_voice_id", "voc_test")
    monkeypatch.setattr(settings, "breezeblue_api_base", "https://api.breeze.blue/v1")
    monkeypatch.setattr(settings, "breezeblue_max_chars", 50)
    monkeypatch.setattr(settings, "breezeblue_daily_limit", 2)


def _patch_http(monkeypatch, captured, audio=b"ID3fake-mp3"):
    """替换 httpx.AsyncClient.post 捕获请求(async context manager 三件套)"""

    class _Resp:
        status_code = 200
        content = audio

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None, params=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["params"] = params
            return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)


def test_get_tts_registers_breezeblue(monkeypatch, _bb_on):
    """get_tts('breezeblue') 返回 BreezeBlueTTSProvider 且读 settings 配置"""
    p = get_tts("breezeblue")
    assert isinstance(p, BreezeBlueTTSProvider)
    assert p.api_key == "brz_test" and p.voice_id == "voc_test" and p.max_chars == 50


def test_get_tts_no_key_falls_back_to_stub(monkeypatch):
    """无 api_key → get_tts('breezeblue') 仍返回 provider,但 synthesize 抛错(调用方回退文本);
    settings.tts_provider=breezeblue 无 key 时 get_tts() 默认路径 → stub(链路不断)"""
    monkeypatch.setattr(settings, "breezeblue_api_key", "")
    monkeypatch.setattr(settings, "breezeblue_voice_id", "voc_test")
    p = BreezeBlueTTSProvider()
    with pytest.raises(RuntimeError):
        asyncio.run(p.synthesize("嗨"))


async def test_synthesize_truncates_and_posts_binary(monkeypatch, _bb_on):
    """超长文本按 max_chars 截断(控费);请求带 xi-api-key 头+output_format=mp3;返回二进制"""
    captured = {}
    _patch_http(monkeypatch, captured)
    p = BreezeBlueTTSProvider()
    # 注入假 redis:真 redis 在线时护栏 INCR 会跨测试累积,超 daily_limit 误拦本测
    from storage.redis_client import get_redis as _gr

    async def fake_gr():
        return _FakeRedis()

    import storage.redis_client as rc
    monkeypatch.setattr(rc, "get_redis", fake_gr)
    audio = await p.synthesize("字" * 80)
    assert audio == b"ID3fake-mp3"
    assert len(captured["json"]["text"]) == 50          # 截断到 max_chars
    assert captured["headers"]["xi-api-key"] == "brz_test"
    assert captured["params"] == {"output_format": "wav"}   # 2026-11-08:wav+尾静音(结尾余韵)
    assert f"/text-to-speech/voc_test" in captured["url"]


async def test_daily_guard_blocks_over_limit(monkeypatch, _bb_on):
    """每日护栏:INCR 超 daily_limit → 抛 RuntimeError(调用方回退文本,不再打 API)"""
    captured = {}
    _patch_http(monkeypatch, captured)
    p = BreezeBlueTTSProvider()
    fake = _FakeRedis(limit_hit_at=2)
    from storage.redis_client import get_redis as _gr

    async def fake_gr():
        return fake

    import storage.redis_client as rc
    monkeypatch.setattr(rc, "get_redis", fake_gr)
    # 第 1、2 次放行(limit=2);第 3 次 INCR=3>2 → 抛
    await p.synthesize("一")
    await p.synthesize("二")
    with pytest.raises(RuntimeError):
        await p.synthesize("三")
    assert captured.get("json") and captured["json"]["text"] in ("一", "二")   # 第三次没打 API


async def test_daily_guard_redis_down_allows(monkeypatch, _bb_on):
    """redis 不可用 → 护栏放行(降级已有,语音非关键路径),照常合成"""
    captured = {}
    _patch_http(monkeypatch, captured)
    p = BreezeBlueTTSProvider()

    async def fake_gr():
        raise RuntimeError("redis down")

    import storage.redis_client as rc
    monkeypatch.setattr(rc, "get_redis", fake_gr)
    audio = await p.synthesize("护栏放行")
    assert audio == b"ID3fake-mp3"


async def test_synthesize_empty_text_short_circuits(monkeypatch, _bb_on):
    """空白文本 → 直接返回空 bytes,不打 API 不计护栏"""
    captured = {}
    _patch_http(monkeypatch, captured)
    p = BreezeBlueTTSProvider()
    assert await p.synthesize("   ") == b""
    assert captured == {}


async def test_synthesize_speed_passthrough(monkeypatch, _bb_on):
    """speed≠1.0 → voice_settings.speed 透传(2026-11-08 用户要求 1.1 倍;
    BreezeBlue 原生 speed=变速不变调,0.5-2.0)"""
    captured = {}
    _patch_http(monkeypatch, captured)
    p = BreezeBlueTTSProvider()
    # 注入假 redis(真 redis 在线时护栏 INCR 跨测试累积会误拦)
    from storage.redis_client import get_redis as _gr

    async def fake_gr():
        return _FakeRedis()

    import storage.redis_client as rc
    monkeypatch.setattr(rc, "get_redis", fake_gr)
    await p.synthesize("语速测试", speed=1.1)
    assert captured["json"]["voice_settings"]["speed"] == 1.1
    await p.synthesize("正常语速", speed=1.0)
    assert "speed" not in captured["json"]["voice_settings"]   # 1.0 不写(默认值)
