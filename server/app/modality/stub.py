"""
Stub 多模态 Provider：不调用真实第三方服务，返回占位 artifact。
作为默认 provider（真实 provider 未配置 / Q-10 未确认时使用），保证链路可跑、便于开发与测试。
真实实现（如 siliconflow 的 TTS/图像端点）待 Q-10 确认后经 register_tts/register_image 注册。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 创建 StubTTSProvider / StubImageProvider
"""
from modality.base import TTSProvider, ImageProvider, AudioArtifact, ImageArtifact


class StubTTSProvider(TTSProvider):
    """占位 TTS：返回 stub:// 音频标识，不合成真实音频"""
    name = "stub"

    async def synthesize(self, text: str, voice: str = "", **opts) -> AudioArtifact:
        return AudioArtifact(url=f"stub://tts/{abs(hash(text))}", provider="stub", format="mp3")


class StubImageProvider(ImageProvider):
    """占位图像：返回 stub:// 图像标识，不生成真实图像"""
    name = "stub"

    async def generate(self, prompt: str, size: str = "", **opts) -> ImageArtifact:
        return ImageArtifact(url=f"stub://img/{abs(hash(prompt))}", provider="stub", format="png")
