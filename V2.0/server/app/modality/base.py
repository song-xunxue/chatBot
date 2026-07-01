"""
多模态 Provider 基类(V2.0,M-vision 2026-07-01)
当前范围:图像理解(VisionProvider)——QQ 收图 → GLM vision 解析成文本 → 进 pipeline。
TTS/图像生成/ASR 暂不移植(V2.0 QQ 文本机器人用不到;按需后扩)。

作者: 李文煜
日期: 2026-07-01

2026-07-01
变更说明：
  1. M-vision 从 V1.0 modality/base.py 移植 VisionProvider ABC(仅视觉,精简)
"""
from abc import ABC, abstractmethod


class VisionProvider(ABC):
    """图像理解 Provider 抽象(多模态视觉:图 bytes + 提示 → 文字描述)"""
    name: str = ""

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def understand(self, image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> str:
        """理解图像内容,按 prompt 返回文字描述。失败由调用方 try/except 软失败兜底。"""
