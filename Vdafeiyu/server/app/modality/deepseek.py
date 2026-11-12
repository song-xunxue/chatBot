"""
DeepSeek 图像理解 Provider —— OpenAI 兼容多模态
复用 DeepSeek chat endpoint(/chat/completions),messages.content 为 list,
含 image_url(data:base64)。模型 deepseek-chat 实测支持图像输入(2026-11-12 探针:
1x1 红色像素问色答「红色」,prompt_tokens 198 vs 纯文本 ~10,图像真实进上下文)。

日期: 2026-11-12

2026-11-12
变更说明：
  1. 新建:GLM vision 账单到期(套餐过期+无余额)后 vision 切 DeepSeek——用户立规
     「以后都改用 deepseek」;payload 形状与 glm.py 同款(OpenAI 兼容),仅 base/model 不同
"""
import base64

import httpx

from core.config import settings

# DeepSeek OpenAI 兼容 base(与 llm/deepseek.py 同端点)
_BASE = "https://api.deepseek.com"


class DeepSeekVisionProvider:
    """DeepSeek 图像理解:多模态 chat(图 + prompt → 文字描述)"""
    name = "deepseek"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or settings.deepseek_api_key
        self.model = model or settings.deepseek_vision_model

    async def understand(self, image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> str:
        # 1.图片转 data URL(OpenAI 多模态格式:image_url 内嵌 base64)
        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:{mime};base64,{b64}"
        # 2.多模态 payload:text 提示 + image_url(deepseek-chat 实测支持 image_url content part)
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
        # 3.调 DeepSeek,返描述文本(调用方负责 try/except 软失败)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{_BASE}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
