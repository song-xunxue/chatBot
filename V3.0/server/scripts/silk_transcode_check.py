"""
SILK 转码链 gating 验证(2026-08-04 M-tts-0)
验证 TTS 产出的 mp3 能否转成 QQ 接受的 Tencent SILK 格式(0x02 前缀)。
链路:mp3 → ffmpeg 24k mono PCM wav → pysilk encode SILK(tencent=True) → decode 回环验证。

依赖(已装):silk-python(pysilk 0.2.8) + ffmpeg(conda-forge 8.1.2,sys.prefix/Library/bin)
输入:scripts/tts_test_output.mp3(real_tts_check.py 产物)
产物:scripts/tts_test_output.silk(不入库,可删)

pysilk 用法(对照 AstrBot tencent_record_helper.py):
  encode(BytesIO(pcm), out_io, rate, rate, tencent=True)  # 0x02 前缀 QQ 兼容流
  decode(BytesIO(silk去0x02), out_io, 24000)              # 回环验证

作者: 李文煜
日期: 2026-08-04
"""
import shutil
import subprocess
import sys
import wave
from io import BytesIO
from pathlib import Path

import pysilk  # silk-python 0.2.8 提供

SCRIPTS = Path(__file__).resolve().parent
MP3_IN = SCRIPTS / "tts_test_output.mp3"
WAV_TMP = SCRIPTS / "_tmp_24k.wav"
SILK_OUT = SCRIPTS / "tts_test_output.silk"


def find_ffmpeg() -> str:
    """定位 ffmpeg(优先 PATH,回退 conda env Library/bin[Win] / bin[Linux])。
    此逻辑后续 utils/silk.py 复用(开发 Windows + 部署 Docker Linux 都覆盖)。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    for c in (Path(sys.prefix) / "Library/bin/ffmpeg.exe",
              Path(sys.prefix) / "bin/ffmpeg"):
        if c.exists():
            return str(c)
    return "ffmpeg"


def mp3_to_wav(mp3: Path, wav: Path, ffmpeg: str) -> None:
    """ffmpeg 归一化为 24000Hz/单声道/16bit PCM WAV(尾部 apad=pad_dur=2 防截断)"""
    cmd = [ffmpeg, "-y", "-i", str(mp3), "-acodec", "pcm_s16le",
           "-ar", "24000", "-ac", "1", "-af", "apad=pad_dur=2",
           "-fflags", "+genpts", "-hide_banner", str(wav)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(f"ffmpeg 失败(returncode {r.returncode}):\n{r.stderr.decode(errors='replace')[-800:]}")
        sys.exit(2)


def wav_to_silk(wav_path: Path, silk_path: Path) -> float:
    """pysilk 编码 WAV(PCM) → Tencent SILK。返回时长秒"""
    with wave.open(str(wav_path), "rb") as w:
        rate = w.getframerate()
        frames = w.getnframes()
        pcm = w.readframes(frames)
    in_io = BytesIO(pcm)
    out_io = BytesIO()
    # tencent=True 出 0x02 前缀 QQ 兼容流;两 rate 参数=输入/输出采样率(均 24000)
    pysilk.encode(in_io, out_io, rate, rate, tencent=True)
    silk_path.write_bytes(out_io.getvalue())
    return frames / rate if rate else 0.0


def silk_decode_roundtrip(silk_path: Path) -> int:
    """回环验证:pysilk decode silk → pcm 字节数(>0 证明 silk 有效可解码)"""
    data = silk_path.read_bytes()
    if data.startswith(b"\x02"):
        data = data[1:]  # 去 0x02 前缀
    in_io = BytesIO(data)
    out_io = BytesIO()
    pysilk.decode(in_io, out_io, 24000)
    return len(out_io.getvalue())


def main():
    if not MP3_IN.is_file():
        print(f"错误:缺 {MP3_IN}(先跑 real_tts_check.py 生成 mp3)"); sys.exit(1)
    ff = find_ffmpeg()
    print(f"ffmpeg: {ff}")
    print(f"pysilk: {getattr(pysilk, '__version__', 'ok')}")
    print("=" * 60)

    # 1. mp3 → wav
    print("[1/3] mp3 -> 24k mono PCM wav")
    mp3_to_wav(MP3_IN, WAV_TMP, ff)
    print(f"  wav: {WAV_TMP.name}  {WAV_TMP.stat().st_size/1024:.1f} KB")

    # 2. wav → silk
    print("[2/3] wav -> Tencent SILK")
    dur = wav_to_silk(WAV_TMP, SILK_OUT)
    silk_bytes = SILK_OUT.read_bytes()
    has_prefix = silk_bytes.startswith(b"\x02")
    print(f"  silk: {SILK_OUT.name}  {len(silk_bytes)/1024:.1f} KB  时长 {dur:.1f}s  0x02前缀={has_prefix}")

    # 3. decode 回环
    print("[3/3] decode 回环验证")
    pcm_len = silk_decode_roundtrip(SILK_OUT)
    print(f"  decode pcm: {pcm_len} bytes ({pcm_len/1024:.1f} KB)")

    WAV_TMP.unlink(missing_ok=True)  # 清理临时 wav
    print("=" * 60)
    ok = has_prefix and pcm_len > 0 and dur > 0
    print(f"总结:silk {len(silk_bytes)}B / 时长 {dur:.1f}s / 0x02前缀 {has_prefix} / decode {pcm_len}B")
    print("gating 结论:" + ("PASS - 转码链打通,mp3->silk 可用,可进 M-tts-1" if ok else "FAIL - 转码异常,需排查"))
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
