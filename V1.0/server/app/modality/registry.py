"""
多模态 Provider 注册表：按名实例化 TTS / Image provider。
当前内置 stub；真实 provider（siliconflow 等）待 Q-10 确认后用 register_tts/register_image 注册。
get_* 对未知名/空名回退 stub，保证链路不崩。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 创建 registry：get_tts/get_image + register_* + stub 回退
"""
from core.config import settings
from modality.base import TTSProvider, ImageProvider, VisionProvider, ASRProvider
from modality.stub import (
    StubTTSProvider, StubImageProvider, StubVisionProvider, StubASRProvider,
)
from modality.siliconflow import SiliconFlowVisionProvider, SiliconFlowASRProvider

_TTS: dict[str, type[TTSProvider]] = {"stub": StubTTSProvider}
_IMAGE: dict[str, type[ImageProvider]] = {"stub": StubImageProvider}
_VISION: dict[str, type[VisionProvider]] = {"stub": StubVisionProvider, "siliconflow": SiliconFlowVisionProvider}
_ASR: dict[str, type[ASRProvider]] = {"stub": StubASRProvider, "siliconflow": SiliconFlowASRProvider}


def register_tts(name: str, cls: type[TTSProvider]) -> None:
    """注册一个 TTS provider 实现（供真实服务接入）"""
    _TTS[name.lower()] = cls


def register_image(name: str, cls: type[ImageProvider]) -> None:
    """注册一个 Image provider 实现（供真实服务接入）"""
    _IMAGE[name.lower()] = cls


def register_vision(name: str, cls: type[VisionProvider]) -> None:
    """注册一个图像理解 provider 实现"""
    _VISION[name.lower()] = cls


def register_asr(name: str, cls: type[ASRProvider]) -> None:
    """注册一个语音识别 provider 实现"""
    _ASR[name.lower()] = cls


def get_tts(name: str = "") -> TTSProvider:
    """按名取 TTS provider 实例；未知名/空名回退 stub"""
    cls = _TTS.get((name or "").lower()) or _TTS["stub"]
    return cls()


def get_image(name: str = "") -> ImageProvider:
    """按名取 Image provider 实例；未知名/空名回退 stub"""
    cls = _IMAGE.get((name or "").lower()) or _IMAGE["stub"]
    return cls()


def get_vision(name: str = "") -> VisionProvider:
    """按名取图像理解 provider 实例；siliconflow 注入 api_key；未知名回退 stub"""
    cls = _VISION.get((name or "").lower()) or _VISION["stub"]
    return cls(api_key=settings.siliconflow_api_key)


def get_asr(name: str = "") -> ASRProvider:
    """按名取语音识别 provider 实例；siliconflow 注入 api_key；未知名回退 stub"""
    cls = _ASR.get((name or "").lower()) or _ASR["stub"]
    return cls(api_key=settings.siliconflow_api_key)


def available_tts() -> list[str]:
    return sorted(_TTS.keys())


def available_image() -> list[str]:
    return sorted(_IMAGE.keys())
