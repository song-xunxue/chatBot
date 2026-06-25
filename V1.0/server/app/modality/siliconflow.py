"""
硅基流动 多模态理解 Provider：图像理解(Vision) + 语音识别(ASR)
- Vision：OpenAI 兼容 /chat/completions，多模态消息(content 为 list，含 image_url data:base64)
- ASR：OpenAI-Whisper 兼容 /audio/transcriptions（multipart 上传音频）
均复用 settings.siliconflow_api_key，base_url 与 llm/siliconflow 一致。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.2 创建硅基流动 Vision/ASR Provider
"""
import base64

import httpx

from core.config import settings
from modality.base import VisionProvider, ASRProvider

_BASE = "https://api.siliconflow.cn/v1"


class SiliconFlowVisionProvider(VisionProvider):
    """硅基流动图像理解：多模态 chat（图 + prompt → 描述）"""
    name = "siliconflow"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model or settings.siliconflow_vision_model

    async def understand(self, image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> str:
        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:{mime};base64,{b64}"
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
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{_BASE}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class SiliconFlowASRProvider(ASRProvider):
    """硅基流动语音识别：Whisper 兼容 /audio/transcriptions（SenseVoice）"""
    name = "siliconflow"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model or settings.siliconflow_asr_model

    async def transcribe(self, audio_bytes: bytes, fmt: str = "wav") -> str:
        files = {"file": (f"audio.{fmt}", audio_bytes, f"audio/{fmt}")}
        data = {"model": self.model}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{_BASE}/audio/transcriptions", headers=headers, files=files, data=data)
            resp.raise_for_status()
            return resp.json().get("text", "")
