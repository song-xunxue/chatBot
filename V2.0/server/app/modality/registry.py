"""
图像理解 Provider registry —— 按名实例化(settings.multimodal_vision_provider 选 glm/stub)
镜像 llm/registry.py 的 get_provider 模式;未配置 key 或未知名降级 stub(链路不断)。

作者: 李文煜
日期: 2026-07-01
"""
from modality.base import VisionProvider
from modality.glm import GLMVisionProvider
from modality.stub import StubVisionProvider
from core.config import settings


def get_vision(name: str = "") -> VisionProvider:
    """取图像理解 provider:优先显式 name,否则 settings.multimodal_vision_provider。
    glm 需配 glm_api_key,否则降级 stub(避免无 key 时崩)。"""
    name = (name or settings.multimodal_vision_provider or "glm").lower()
    if name == "glm":
        if not settings.glm_api_key:
            return StubVisionProvider()   # 无 key 降级 stub
        return GLMVisionProvider()
    if name == "stub":
        return StubVisionProvider()
    return StubVisionProvider()           # 未知 provider 名降级 stub
