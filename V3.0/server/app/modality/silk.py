"""
音频 → Tencent SILK 转码(M-tts,2026-08-04)
QQ 官方机器人语音消息必须 SILK 格式(0x02 前缀);TTS 产出 mp3 经本模块转 silk 才能发。

链路(对照 AstrBot tencent_record_helper.py + 本项目 gating 验证):
  音频 bytes(mp3/wav) → ffmpeg 归一化 24000Hz/单声道/16bit PCM wav → pysilk encode(tencent=True)
  → 0x02 前缀 QQ 兼容 SILK bytes → base64 上传 /v2/users/{openid}/files

依赖:silk-python(pysilk) + ffmpeg(系统二进制;开发 conda 装 / 部署 Dockerfile 装)
ffmpeg 定位:优先 PATH,回退 conda env Library/bin[Win] / bin[Linux](开发+部署都覆盖)

作者: 李文煜
日期: 2026-08-04
"""
import asyncio
import io
import logging
import os
import shutil
import sys
import tempfile
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


def find_ffmpeg() -> str:
    """定位 ffmpeg 可执行:优先 PATH(shutil.which),回退 conda env Library/bin(Windows) / bin(Linux)。
    开发(Windows conda mychat)与部署(Docker Linux 系统装)都覆盖;找不到返 'ffmpeg' 交由调用时报错。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    for c in (Path(sys.prefix) / "Library/bin/ffmpeg.exe",
              Path(sys.prefix) / "bin/ffmpeg"):
        if c.exists():
            return str(c)
    return "ffmpeg"


async def to_tencent_silk(audio_bytes: bytes, *, ffmpeg: str = "") -> bytes:
    """任意音频 bytes(mp3/wav/...) → Tencent SILK bytes(0x02 前缀,QQ 兼容)。

    用 asyncio 子进程跑 ffmpeg(不阻塞事件循环);pysilk 编码短音频 CPU 耗时低(~ms)。
    失败抛 RuntimeError(调用方软失败:记日志,跳过语音,fallback 纯文本回复)。

    参数:
        audio_bytes: 输入音频(TTS 产出的 mp3)
        ffmpeg: ffmpeg 路径(空=自动 find_ffmpeg)
    返回:
        SILK bytes(首字节 0x02)
    """
    import pysilk  # 延迟导入:silk-python 是 TTS 专属重依赖,无 TTS 时不强制装

    ff = ffmpeg or find_ffmpeg()
    tmpdir = tempfile.mkdtemp(prefix="tts_silk_")
    src_path = Path(tmpdir) / "in.mp3"
    wav_path = Path(tmpdir) / "24k.wav"
    try:
        src_path.write_bytes(audio_bytes)
        # ffmpeg 归一化:24000Hz/单声道/16bit PCM wav;apad=pad_dur=2 尾部静音防截断
        proc = await asyncio.create_subprocess_exec(
            ff, "-y", "-i", str(src_path),
            "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
            "-af", "apad=pad_dur=2", "-fflags", "+genpts", "-hide_banner",
            str(wav_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            tail = stderr.decode(errors="replace")[-400:] if stderr else ""
            raise RuntimeError(f"ffmpeg 归一化失败(returncode {proc.returncode}): {tail}")
        # pysilk 编码:读 PCM → encode(tencent=True 出 0x02 前缀 QQ 兼容流)
        with wave.open(str(wav_path), "rb") as w:
            rate = w.getframerate()
            pcm = w.readframes(w.getnframes())
        out = io.BytesIO()
        pysilk.encode(io.BytesIO(pcm), out, rate, rate, tencent=True)
        silk = out.getvalue()
        if not silk:
            raise RuntimeError("pysilk encode 产出空 silk")
        return silk
    finally:
        # 清理临时文件(避免磁盘堆积;AstrBot 同款 cleanup 逻辑)
        for f in (src_path, wav_path):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
