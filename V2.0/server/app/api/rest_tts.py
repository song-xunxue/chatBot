"""
TTS 语音预览 REST 接口(M-tts,2026-08-04):面板音色试听。
给定音色(可选文本)→ 实时合成 mp3 返回前端播放。固定预览文本便于横向对比各音色。

路由(prefix /api/v1):
  POST /tts/preview   body{voice, text?} → audio/mpeg mp3 bytes

作者: 李文煜
日期: 2026-08-04
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response

from api._auth import verify_token
from modality.tts import TTS_VOICES, get_tts

router = APIRouter(prefix="/api/v1", tags=["tts"])

# 固定预览文本(角色口吻;所有音色用同一句便于横向对比听感)
PREVIEW_TEXT = "夫君，今天辛苦啦，早点休息哦。"


@router.post("/tts/preview", dependencies=[Depends(verify_token)])
async def preview_tts(body: dict = Body(...)):
    """音色试听:给定 voice 合成预览文本 → 返 mp3 bytes(audio/mpeg),前端 Audio.play 播放。

    参数:
        voice: 音色名(须在 TTS_VOICES 4 女声内,防注入)
        text:  可选自定义文本(空=用固定 PREVIEW_TEXT)
    失败:TTS 异常或 stub 空产出 → 503(无 key/降级时前端提示无法预览)。
    """
    voice = str(body.get("voice", "")).strip()
    if voice not in TTS_VOICES:
        raise HTTPException(status_code=400, detail=f"无效音色,可选: {list(TTS_VOICES.keys())}")
    text = str(body.get("text") or PREVIEW_TEXT)
    try:
        mp3 = await get_tts().synthesize(text, voice)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"TTS 合成失败: {e}")
    if not mp3:
        raise HTTPException(status_code=503, detail="TTS 未配置(无 SILICONFLOW_API_KEY),无法预览")
    return Response(content=mp3, media_type="audio/mpeg")
