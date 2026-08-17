"""
TTS 预览端点单测(M-tts,2026-08-04)
覆盖:POST /tts/preview 合成 mp3 返 audio/mpeg(固定预览文本)+ 自定义文本 + 无效音色 400
+ stub 空产出 503 + 合成异常 503。直调端点函数(绕过 Depends),mock get_tts.synthesize。

作者: 李文煜
日期: 2026-08-04
"""
import pytest
from fastapi import HTTPException

import api.rest_tts as rt
import modality.tts as tts_mod

_captured: dict = {}


def _patch(monkeypatch, *, mp3=b"MP3BYTES", exc=None):
    class FakeProvider:
        async def synthesize(self, text, voice, speed=1.0, gain=0.0, emotion=""):
            _captured["text"] = text
            _captured["voice"] = voice
            if exc:
                raise exc
            return mp3
    monkeypatch.setattr(rt, "get_tts", lambda: FakeProvider())   # patch rest_tts 的 import 引用,非 tts_mod


async def test_preview_returns_mp3(monkeypatch):
    """有效音色 → 200 audio/mpeg + mp3 bytes;用固定预览文本(未传 text)"""
    _patch(monkeypatch, mp3=b"AUDIO123")
    resp = await rt.preview_tts({"voice": "claire"})
    assert resp.status_code == 200
    assert resp.media_type == "audio/mpeg"
    assert resp.body == b"AUDIO123"
    assert _captured == {"text": rt.PREVIEW_TEXT, "voice": "claire"}


async def test_preview_custom_text(monkeypatch):
    """传 text → 用自定义文本合成"""
    _patch(monkeypatch)
    await rt.preview_tts({"voice": "anna", "text": "自定义句子"})
    assert _captured["text"] == "自定义句子"


async def test_preview_invalid_voice_400(monkeypatch):
    """音色不在 TTS_VOICES → 400(防注入)"""
    _patch(monkeypatch)
    with pytest.raises(HTTPException) as ei:
        await rt.preview_tts({"voice": "hacker"})
    assert ei.value.status_code == 400


async def test_preview_stub_empty_503(monkeypatch):
    """stub 空产出(无 key)→ 503"""
    _patch(monkeypatch, mp3=b"")
    with pytest.raises(HTTPException) as ei:
        await rt.preview_tts({"voice": "claire"})
    assert ei.value.status_code == 503


async def test_preview_synth_error_503(monkeypatch):
    """合成异常 → 503"""
    _patch(monkeypatch, exc=RuntimeError("API 挂"))
    with pytest.raises(HTTPException) as ei:
        await rt.preview_tts({"voice": "claire"})
    assert ei.value.status_code == 503
