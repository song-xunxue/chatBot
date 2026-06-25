"""
多模态 Provider 基类与数据载体
镜像 llm/base.py 的 Provider 抽象思路：定义 TTSProvider / ImageProvider 抽象基类 +
AudioArtifact / ImageArtifact 数据载体。具体实现（stub / siliconflow 等）经 registry 按名实例化。
对应 F-P-01(TTS) / F-P-02(image) / F-P-03(sticker)。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 创建基类与载体：synthesize / generate 抽象方法
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AudioArtifact:
    """TTS 产出：音频访问 URL / 本地路径 / 格式 / 来源 provider"""
    url: str = ""
    path: str = ""
    format: str = "mp3"
    provider: str = ""


@dataclass
class ImageArtifact:
    """图像产出：URL / 本地路径 / 格式 / 来源 provider"""
    url: str = ""
    path: str = ""
    format: str = "png"
    provider: str = ""


class TTSProvider(ABC):
    """语音合成 Provider 抽象"""
    name: str = ""

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "", **opts) -> AudioArtifact:
        """把文本合成为语音，返回 AudioArtifact"""


class ImageProvider(ABC):
    """图像生成 Provider 抽象"""
    name: str = ""

    @abstractmethod
    async def generate(self, prompt: str, size: str = "", **opts) -> ImageArtifact:
        """按 prompt 生成图像，返回 ImageArtifact"""


class VisionProvider(ABC):
    """图像理解 Provider 抽象（多模态视觉：图 + 提示 → 文字描述）"""
    name: str = ""

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def understand(self, image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> str:
        """理解图像内容，按 prompt 返回文字描述"""


class ASRProvider(ABC):
    """语音识别 Provider 抽象（音频 → 文字）"""
    name: str = ""

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, fmt: str = "wav") -> str:
        """把音频转写为文字"""
