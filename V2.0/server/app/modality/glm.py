"""
GLM(智谱)图像理解 Provider —— OpenAI 兼容多模态
复用 GLM 文本 endpoint(/api/paas/v4/chat/completions),messages.content 为 list,
含 image_url(data:base64)。模型默认 glm-4v-flash(轻量 free);可经 .env GLM_VISION_MODEL 切换。

作者: 李文煜
日期: 2026-07-01

2026-07-01
变更说明：
  1. M-vision 新建 GLM 图像理解 Provider(glm-4v,移植自 V1.0 siliconflow.py 模式)
"""
import base64

import httpx

from core.config import settings
from modality.base import VisionProvider

# GLM OpenAI 兼容 base(与 llm/glm.py 一致)
_BASE = "https://open.bigmodel.cn/api/paas/v4"


class GLMVisionProvider(VisionProvider):
    """GLM 图像理解:多模态 chat(图 + prompt → 文字描述)"""
    name = "glm"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or settings.glm_api_key
        self.model = model or settings.glm_vision_model

    async def understand(self, image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> str:
        # 1.图片转 data URL(OpenAI 多模态格式:image_url 内嵌 base64)
        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:{mime};base64,{b64}"
        # 2.多模态 payload:text 提示 + image_url(GLM-4V 与 OpenAI 兼容)
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        # 3.调 GLM,返描述文本(调用方负责 try/except 软失败)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{_BASE}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
