"""
克隆音色管理单测(M-tts-7,2026-08-04)
覆盖:resolve_voice(克隆 uri 优先/回退预设)+ preview 放开克隆 uri 白名单 + 活跃音色 get/set 端点
+ upload(音频,mock 硅基流动)+ list(代理)。视频提取(_extract_audio_clip)依赖 ffmpeg,部署后人工验证。

作者: 李文煜
日期: 2026-08-04
"""
import io

import httpx
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

import api.rest_tts as rt
from modality.tts import resolve_voice


# —— resolve_voice(克隆 uri 优先)——
class _FakeRedis:
    def __init__(self, store=None):
        self.store = store or {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v):
        self.store[k] = v

    async def delete(self, k):
        self.store.pop(k, None)


async def test_resolve_voice_uses_clone_uri():
    """Redis 存了克隆 uri → 返 uri(优先于预设)"""
    r = _FakeRedis({"mychat:tts:custom_voice:oid1": "speech:clone:x:y"})
    assert await resolve_voice(r, "oid1", "claire") == "speech:clone:x:y"


async def test_resolve_voice_fallback_preset():
    """未设克隆 uri → 回退预设"""
    r = _FakeRedis()
    assert await resolve_voice(r, "oid1", "anna") == "anna"


async def test_resolve_voice_none_redis():
    """redis=None → 直接回退(不抛)"""
    assert await resolve_voice(None, "oid1", "claire") == "claire"


# —— preview 放开克隆 uri 白名单 ——
def _patch_provider(monkeypatch, mp3=b"MP3"):
    class FakeProvider:
        async def synthesize(self, text, voice, speed=1.0, gain=0.0, emotion=""):
            _patch_provider.captured = voice
            return mp3
    monkeypatch.setattr(rt, "get_tts", lambda: FakeProvider())   # patch rt 的 import 引用


async def test_preview_clone_uri_allowed(monkeypatch):
    """克隆 uri(speech:...)通过白名单,透传给 synthesize"""
    _patch_provider(monkeypatch)
    resp = await rt.preview_tts({"voice": "speech:my-voice:abc:def"})
    assert resp.status_code == 200
    assert _patch_provider.captured == "speech:my-voice:abc:def"


async def test_preview_preset_still_allowed(monkeypatch):
    """预设音色仍可用"""
    _patch_provider(monkeypatch)
    await rt.preview_tts({"voice": "claire"})
    assert _patch_provider.captured == "claire"


async def test_preview_invalid_rejected(monkeypatch):
    """非预设非克隆 uri → 400"""
    _patch_provider(monkeypatch)
    with pytest.raises(HTTPException) as ei:
        await rt.preview_tts({"voice": "hack"})
    assert ei.value.status_code == 400


# —— 活跃音色 get/set 端点 ——
async def test_active_voice_get_set(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rt, "get_redis", lambda: _async_return(fake))
    got = await rt.get_active_voice("oid1")
    assert got == {"object_id": "oid1", "uri": None}
    await rt.set_active_voice("oid1", body={"uri": "speech:x:y:z"})
    assert await rt.get_active_voice("oid1") == {"object_id": "oid1", "uri": "speech:x:y:z"}
    await rt.set_active_voice("oid1", body={})  # 空=清除
    assert await rt.get_active_voice("oid1") == {"object_id": "oid1", "uri": None}


# —— upload(音频,mock 硅基流动)+ list ——
def _patch_httpx(monkeypatch, handler):
    """patch rt.httpx.AsyncClient 走 MockTransport"""
    real = httpx.AsyncClient

    def factory(**kw):
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(rt, "httpx", type("M", (), {"AsyncClient": staticmethod(factory)}))


async def test_upload_audio_returns_uri(monkeypatch):
    """上传音频(非视频)→ 透传硅基流动 → 返 uri"""
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"uri": "speech:test:u:v"})

    _patch_httpx(monkeypatch, handler)
    monkeypatch.setattr(rt.settings, "siliconflow_api_key", "sk-fake")
    f = UploadFile(filename="ref.mp3", file=io.BytesIO(b"AUDIOBYTES"))
    out = await rt.upload_voice(file=f, customName="myvoice", text="你好", start_sec=0, dur_sec=0)
    assert out == {"uri": "speech:test:u:v", "customName": "myvoice"}
    assert "/uploads/audio/voice" in captured["url"]


async def test_upload_403_realname(monkeypatch):
    """硅基流动返 403 → 端点转 403(账号未实名提示)"""
    _patch_httpx(monkeypatch, lambda r: httpx.Response(403, json={"msg": "not realname"}))
    monkeypatch.setattr(rt.settings, "siliconflow_api_key", "sk-fake")
    f = UploadFile(filename="ref.mp3", file=io.BytesIO(b"X"))
    with pytest.raises(HTTPException) as ei:
        await rt.upload_voice(file=f, customName="v", text="", start_sec=0, dur_sec=0)
    assert ei.value.status_code == 403


async def test_list_voices_proxy(monkeypatch):
    """list 代理硅基流动返回"""
    _patch_httpx(monkeypatch, lambda r: httpx.Response(
        200, json={"result": [{"customName": "a", "uri": "speech:a:x:y"}]}))
    monkeypatch.setattr(rt.settings, "siliconflow_api_key", "sk-fake")
    out = await rt.list_voices()
    assert out["result"][0]["customName"] == "a"


async def _async_return(val):
    return val
