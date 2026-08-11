"""
GPT-SoVITS 就绪状态检测单测(M-tts-2,2026-08-10)
覆盖:check_gptsovits_status 心跳命中/主动探测/force 强探/probe=False 不探/非 gptsovits 不探/config 缺失
六大分支 + 在线/离线探测。核心契约:心跳缓存命中绝不探测 frp(免重复打隧道)。

作者: 李文煜
日期: 2026-08-10
"""
import json

import httpx

from modality import tts as tts_mod
from modality.tts import HEARTBEAT_KEY, check_gptsovits_status


def _patch_sync_client(monkeypatch, handler):
    """patch httpx.Client 让 _sync_probe 走 MockTransport(同 test_tts.py 的 _patch_sync_client)。"""
    real = httpx.Client

    def factory(**kw):
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(httpx, "Client", factory)


class FakeRedis:
    """async Redis 最小桩:get/set/delete(够 check_gptsovits_status 用)。"""
    def __init__(self, data=None):
        self._data = data or {}

    async def get(self, key):
        return self._data.get(key)

    async def set(self, key, val, ex=None):
        self._data[key] = val

    async def delete(self, key):
        self._data.pop(key, None)


def _set_gptsovits(monkeypatch, provider="gptsovits", ref="/ref.wav",
                   gpt="m.ckpt", sovits="m.pth"):
    """统一设 gptsovits provider + 完整 config(默认全配齐;单测按需置空)。"""
    monkeypatch.setattr(tts_mod.settings, "tts_provider", provider)
    monkeypatch.setattr(tts_mod.settings, "gptsovits_api_base", "http://x:9880")
    monkeypatch.setattr(tts_mod.settings, "gptsovits_ref_audio", ref)
    monkeypatch.setattr(tts_mod.settings, "gptsovits_gpt_model", gpt)
    monkeypatch.setattr(tts_mod.settings, "gptsovits_sovits_model", sovits)


async def test_status_heartbeat_hit_no_probe(monkeypatch):
    """心跳缓存命中 → source=heartbeat/reachable=True,且绝不发 HTTP(免打 frp,核心契约)"""
    _set_gptsovits(monkeypatch)
    called = []

    def handler(req):
        called.append(str(req.url))
        return httpx.Response(200)

    _patch_sync_client(monkeypatch, handler)
    redis = FakeRedis({HEARTBEAT_KEY: json.dumps({"ready": True, "ts": 123, "latency_ms": 5})})
    res = await check_gptsovits_status(redis)
    assert res["source"] == "heartbeat"
    assert res["reachable"] is True
    assert res["heartbeat_ts"] == 123
    assert res["config_ok"] is True
    assert called == []  # 心跳命中,未探测


async def test_status_probe_when_no_heartbeat(monkeypatch):
    """无心跳 + probe=True → 主动探测根路径;handler 200 → reachable=True/source=probe"""
    _set_gptsovits(monkeypatch)

    def handler(req):
        assert "9880" in str(req.url)   # 探测 9880 根路径
        return httpx.Response(200)

    _patch_sync_client(monkeypatch, handler)
    res = await check_gptsovits_status(FakeRedis())  # 无心跳
    assert res["source"] == "probe"
    assert res["reachable"] is True
    assert res["latency_ms"] >= 0


async def test_status_probe_offline(monkeypatch):
    """无心跳 + probe=True + 探测连接被拒 → reachable=False/detail 含未连接"""
    _set_gptsovits(monkeypatch)

    def handler(req):
        raise httpx.ConnectError("refused")

    _patch_sync_client(monkeypatch, handler)
    res = await check_gptsovits_status(FakeRedis())
    assert res["source"] == "probe"
    assert res["reachable"] is False
    assert "未连接" in res["detail"]


async def test_status_probe_false_skips_probe(monkeypatch):
    """无心跳 + probe=False → 不探测(折叠态/轮询:零 frp 开销)"""
    _set_gptsovits(monkeypatch)
    called = []

    def handler(req):
        called.append(1)
        return httpx.Response(200)

    _patch_sync_client(monkeypatch, handler)
    res = await check_gptsovits_status(FakeRedis(), probe=False)
    assert res["source"] == "none"
    assert res["reachable"] is False
    assert called == []


async def test_status_force_skips_heartbeat(monkeypatch):
    """有心跳 + force=True → 跳心跳强探(手动「重新检测」按钮)"""
    _set_gptsovits(monkeypatch)
    called = []

    def handler(req):
        called.append(1)
        return httpx.Response(200)

    _patch_sync_client(monkeypatch, handler)
    redis = FakeRedis({HEARTBEAT_KEY: json.dumps({"ready": True, "ts": 999})})
    res = await check_gptsovits_status(redis, force=True)
    assert res["source"] == "probe"  # force 跳了心跳,走探测
    assert called == [1]


async def test_status_non_gptsovits_no_probe(monkeypatch):
    """provider=siliconflow → 不探测,source=none,detail 提示非本地"""
    _set_gptsovits(monkeypatch, provider="siliconflow")
    called = []

    def handler(req):
        called.append(1)
        return httpx.Response(200)

    _patch_sync_client(monkeypatch, handler)
    res = await check_gptsovits_status(FakeRedis())
    assert res["source"] == "none"
    assert "siliconflow" in res["detail"]
    assert called == []


async def test_status_config_missing(monkeypatch):
    """ref_audio/gpt/sovits 空 → config_ok=False/missing 全含"""
    _set_gptsovits(monkeypatch, ref="", gpt="", sovits="")

    def handler(req):
        return httpx.Response(200)

    _patch_sync_client(monkeypatch, handler)
    res = await check_gptsovits_status(FakeRedis())
    assert res["config_ok"] is False
    assert "ref_audio" in res["missing"]
    assert "gpt_model" in res["missing"]
    assert "sovits_model" in res["missing"]
