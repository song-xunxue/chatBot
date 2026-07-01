"""modality 包导出(V2.0 M-vision):图像理解 provider 注册表 + 基类"""
from modality.registry import get_vision
from modality.base import VisionProvider

__all__ = ["get_vision", "VisionProvider"]
