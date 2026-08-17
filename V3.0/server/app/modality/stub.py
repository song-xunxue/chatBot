"""
图像理解 Stub Provider —— 无 GLM key 或解析失败时的降级占位
不调真 API,返回固定占位文本(供测试 + key 未配时链路不断)。

作者: 李文煜
日期: 2026-07-01
"""
from modality.base import VisionProvider


class StubVisionProvider(VisionProvider):
    """占位视觉 provider:返回提示性文本,不调外部 API"""
    name = "stub"

    async def understand(self, image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> str:
        return "[图像理解未配置](stub provider)"
