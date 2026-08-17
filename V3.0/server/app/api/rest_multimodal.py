"""
多模态 REST 接口(M-vision,2026-07-01):图像理解上传 → GLM vision 文本描述。
面板/调试用(QQ 收图自动解析走 webhook 内嵌链路);鉴权 X-Access-Token。

路由(prefix /api/v1):
  POST /multimodal/vision   上传图片(UploadFile)→ {description}(软失败返 error,不抛 500)

作者: 李文煜
日期: 2026-07-01

2026-07-01
变更说明：
  1. M-vision 新建图像理解 REST 端点(GLM glm-4v;复用 modality.get_vision)
"""
import logging

from fastapi import APIRouter, Depends, UploadFile, File

from api._auth import verify_token
from modality import get_vision
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["multimodal"])

_MAX_BYTES = 8 * 1024 * 1024   # 8MB 上限(防超大图打爆 GLM vision)


@router.post("/multimodal/vision", dependencies=[Depends(verify_token)])
async def vision_describe(file: UploadFile = File(...)):
    """上传图片 → GLM vision 文本描述。
    软失败:解析失败返 {description:"", error:"..."} 不抛 500(便于面板友好提示)。"""
    raw = await file.read()
    if len(raw) > _MAX_BYTES:
        return {"description": "", "error": "图片过大(>8MB)"}
    mime = file.content_type or "image/jpeg"
    try:
        vision = get_vision()
        desc = await vision.understand(raw, settings.multimodal_vision_prompt, mime)
        return {"description": desc}
    except Exception as e:
        logger.warning("vision REST 解析失败: %s", e)
        return {"description": "", "error": f"图片解析失败: {e}"}
