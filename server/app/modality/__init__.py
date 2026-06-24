"""
多模态服务（TTS / Image）包入口
导出 Provider 基类、数据载体与 registry 取用函数。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 创建 modality 包：TTS/Image Provider 抽象 + stub 默认实现 + registry
"""
from modality.base import (
    TTSProvider, ImageProvider, AudioArtifact, ImageArtifact,
)
from modality.registry import get_tts, get_image, register_tts, register_image

__all__ = [
    "TTSProvider", "ImageProvider", "AudioArtifact", "ImageArtifact",
    "get_tts", "get_image", "register_tts", "register_image",
]
