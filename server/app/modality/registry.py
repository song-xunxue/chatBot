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
from modality.base import TTSProvider, ImageProvider
from modality.stub import StubTTSProvider, StubImageProvider

_TTS: dict[str, type[TTSProvider]] = {"stub": StubTTSProvider}
_IMAGE: dict[str, type[ImageProvider]] = {"stub": StubImageProvider}


def register_tts(name: str, cls: type[TTSProvider]) -> None:
    """注册一个 TTS provider 实现（供真实服务接入）"""
    _TTS[name.lower()] = cls


def register_image(name: str, cls: type[ImageProvider]) -> None:
    """注册一个 Image provider 实现（供真实服务接入）"""
    _IMAGE[name.lower()] = cls


def get_tts(name: str = "") -> TTSProvider:
    """按名取 TTS provider 实例；未知名/空名回退 stub"""
    cls = _TTS.get((name or "").lower()) or _TTS["stub"]
    return cls()


def get_image(name: str = "") -> ImageProvider:
    """按名取 Image provider 实例；未知名/空名回退 stub"""
    cls = _IMAGE.get((name or "").lower()) or _IMAGE["stub"]
    return cls()


def available_tts() -> list[str]:
    return sorted(_TTS.keys())


def available_image() -> list[str]:
    return sorted(_IMAGE.keys())
