"""
modality provider 抽象测试：默认 stub、synthesize/generate 产出载体、register 回退。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 覆盖 modality registry 与 stub provider
"""
from modality import (
    get_tts, get_image, register_tts, register_image,
    AudioArtifact, ImageArtifact, TTSProvider, ImageProvider,
)


async def test_default_stub_tts():
    p = get_tts()
    assert p.name == "stub"
    art = await p.synthesize("你好")
    assert isinstance(art, AudioArtifact)
    assert art.url.startswith("stub://tts/")
    assert art.provider == "stub"


async def test_default_stub_image():
    p = get_image()
    assert p.name == "stub"
    art = await p.generate("一只猫")
    assert isinstance(art, ImageArtifact)
    assert art.url.startswith("stub://img/")
    assert art.provider == "stub"


async def test_register_custom_and_fallback():
    class MyTts(TTSProvider):
        name = "mine"
        async def synthesize(self, text, voice="", **opts):
            return AudioArtifact(url="mine://x", provider="mine")

    class MyImg(ImageProvider):
        name = "mine"
        async def generate(self, prompt, size="", **opts):
            return ImageArtifact(url="mine://img", provider="mine")

    register_tts("mine", MyTts)
    register_image("mine", MyImg)
    assert get_tts("mine").name == "mine"
    assert get_image("mine").name == "mine"
    assert get_tts("nonexistent").name == "stub"      # 未知名回退 stub
    assert get_image("").name == "stub"                # 空名回退 stub
