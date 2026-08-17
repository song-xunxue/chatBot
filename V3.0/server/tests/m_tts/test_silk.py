"""
silk 转码单测(M-tts,2026-08-04)
覆盖:find_ffmpeg 返回路径;to_tencent_silk 真实转码(正弦波 WAV→silk,0x02 前缀 + decode 回环);
非音频输入 → RuntimeError。依赖 ffmpeg+pysilk,缺失则 skip(不阻塞主套件)。

作者: 李文煜
日期: 2026-08-04
"""
import io
import math
import struct
import wave

import pytest

from modality.silk import find_ffmpeg, to_tencent_silk


def _sine_wav_bytes(freq=440, duration=0.5, rate=44100) -> bytes:
    """生成正弦波 WAV bytes(44100Hz/单声道/16bit;测试 fixture,无需外部音频文件)"""
    n = int(rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(32000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(n)
        )
        w.writeframes(frames)
    return buf.getvalue()


def _have_ffmpeg() -> bool:
    return find_ffmpeg() != "ffmpeg"


def _have_pysilk() -> bool:
    try:
        import pysilk  # noqa: F401
        return True
    except ImportError:
        return False


def test_find_ffmpeg_returns_str():
    """find_ffmpeg 返非空字符串(PATH 或 conda env)"""
    ff = find_ffmpeg()
    assert isinstance(ff, str) and ff


async def test_to_tencent_silk_real():
    """真实转码 WAV→silk:产出非空 + 0x02 前缀 + decode 回环成 pcm(整链路验证)"""
    if not _have_ffmpeg() or not _have_pysilk():
        pytest.skip("无 ffmpeg 或 pysilk,跳过真实转码测试")
    silk = await to_tencent_silk(_sine_wav_bytes())
    assert silk[:1] == b"\x02"            # 0x02 前缀(QQ 兼容)
    assert len(silk) > 20
    # decode 回环验证 silk 有效可解码
    import pysilk
    data = silk[1:] if silk.startswith(b"\x02") else silk
    out = io.BytesIO()
    pysilk.decode(io.BytesIO(data), out, 24000)
    assert len(out.getvalue()) > 0


async def test_to_tencent_silk_bad_audio_raises():
    """非音频输入 → ffmpeg 失败抛 RuntimeError(调用方软失败 fallback 文本)"""
    if not _have_ffmpeg():
        pytest.skip("无 ffmpeg,跳过")
    with pytest.raises(RuntimeError):
        await to_tencent_silk(b"this is not audio at all", ffmpeg=find_ffmpeg())
