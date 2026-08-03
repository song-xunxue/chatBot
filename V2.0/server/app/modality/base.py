"""
多模态 Provider 基类(V2.0,M-vision 2026-07-01)
当前范围:图像理解(VisionProvider)——QQ 收图 → GLM vision 解析成文本 → 进 pipeline。
图像生成/ASR 暂不移植;TTS 已加(2026-08-04 M-tts,见 modality/tts.py)。

作者: 李文煜
日期: 2026-07-01

2026-07-01
变更说明：
  1. M-vision 从 V1.0 modality/base.py 移植 VisionProvider ABC(仅视觉,精简)

2026-08-04
变更说明：
  1. M-tts 新增 TTSProvider ABC(文本→音频 bytes),与 VisionProvider 并列
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


class TTSProvider(ABC):
    """语音合成 Provider 抽象(文本 → 音频 bytes)。M-tts 2026-08-04。
    emotion 非空时由子类按模型特定方式注入(如 CosyVoice2 的 <|endofprompt|> 指令)。"""
    name: str = ""

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def synthesize(self, text: str, voice: str, speed: float = 1.0,
                         gain: float = 0.0, emotion: str = "") -> bytes:
        """文本 → 音频 bytes(mp3)。失败抛异常,由调用方 try/except 软失败兜底(跳过语音 fallback 文本)。

        参数:
            text: 要合成的文本
            voice: 音色名(如 claire;子类拼成完整 voice 串)
            speed: 语速 0.25-4.0(1.0 默认)
            gain: 增益 dB -10~10(0 默认)
            emotion: 情感/语气描述(空=纯文本;非空=作情感指令注入)
        """
