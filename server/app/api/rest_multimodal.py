"""
多模态理解 REST：图像理解(vision) / 语音识别(asr)。对应 M6.2。
均经 modality provider 抽象（默认硅基流动；无 key/测试用 stub）；结果为文本，
客户端拿到后作为用户输入送入聊天管道（最小侵入、复用既有流式回复）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.2 创建 rest_multimodal：POST /vision /asr
"""
import logging

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile

from core.config import settings
from modality import get_asr, get_vision

router = APIRouter(prefix="/api/v1", tags=["multimodal"])
logger = logging.getLogger(__name__)

_MAX_BYTES = 8 * 1024 * 1024   # 8MB 上限


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖：Header 或 query 任一通过；显式拒绝空 token"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


@router.post("/multimodal/vision", dependencies=[Depends(_auth)])
async def understand_image(file: UploadFile = File(...),
                           prompt: str = "请简要描述这张图片的内容"):
    """图像理解：上传图片 + prompt → 文字描述（客户端再作为用户消息发送）"""
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件过大(>8MB)")
    provider = get_vision(settings.multimodal_vision_provider)
    try:
        text = await provider.understand(data, prompt, mime=(file.content_type or "image/jpeg"))
    except Exception as e:
        logger.exception("vision understand failed")
        raise HTTPException(status_code=502, detail=f"图像理解失败: {e}")
    return {"text": text}


@router.post("/multimodal/asr", dependencies=[Depends(_auth)])
async def transcribe_audio(file: UploadFile = File(...)):
    """语音识别：上传音频 → 文字（客户端再作为用户消息发送）"""
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件过大(>8MB)")
    ext = (file.filename or "audio.wav").rsplit(".", 1)[-1].lower() or "wav"
    provider = get_asr(settings.multimodal_asr_provider)
    try:
        text = await provider.transcribe(data, fmt=ext)
    except Exception as e:
        logger.exception("asr transcribe failed")
        raise HTTPException(status_code=502, detail=f"语音识别失败: {e}")
    return {"text": text}
