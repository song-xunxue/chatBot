"""
长参考素材切段克隆优化(M-tts 自定义音色,2026-08-04)
硅基流动 zero-shot 克隆单段<30s(8-10s 最佳),长素材超限;切段分别克隆,各合成同一句,
用户试听各样本挑最像目标的段(因 zero-shot 单参考,效果取决于该段质量,多段=多候选选优)。

链路:probe 时长 → 切 N 段(每段 seg_len 秒,尾段<8s 跳过)→ ffmpeg 归一化(mono 16k loudnorm)
→ 上传硅基流动克隆拿 uri → 用 uri 合成同一测试句 → 存 clone_samples/seg_N.mp3 + uris.json

用法:python clone_segments.py <audio_or_video> [seg_len=15] [test_text]
产物:同级 clone_samples/seg_N.mp3(对比试听)+ uris.json(各段 uri,挑中后据此设当前音色)

作者: 李文煜
日期: 2026-08-04
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

ENV = Path(__file__).resolve().parents[2] / ".env"
API = "https://api.siliconflow.cn/v1"
MODEL = "FunAudioLLM/CosyVoice2-0.5B"
TEST_TEXT = "夫君，今天辛苦啦，早点休息哦。"
MIN_SEG = 8   # 段长下限(秒),<8s 克隆不稳,跳过


def _ffmpeg() -> str:
    return (shutil.which("ffmpeg")
            or r"C:\Users\26904\anaconda3\envs\mychat\Library\bin\ffmpeg.exe")


def _ffprobe() -> str:
    return (shutil.which("ffprobe")
            or r"C:\Users\26904\anaconda3\envs\mychat\Library\bin\ffprobe.exe")


def load_key() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("SILICONFLOW_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def probe_duration(f: Path) -> float:
    r = subprocess.run([_ffprobe(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(f)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def normalize_segment(src: Path, start: float, length: float, out: Path) -> bool:
    """切 [start, start+length] → mono 16k loudnorm 响度均衡 → mp3 192k(克隆参考最佳格式)"""
    cmd = [_ffmpeg(), "-y", "-ss", str(start), "-t", str(length), "-i", str(src),
           "-vn", "-ac", "1", "-ar", "16000",
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
           "-c:a", "libmp3lame", "-b:a", "192k", str(out)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def upload_clone(key: str, mp3_bytes: bytes, name: str):
    files = {"file": ("ref.mp3", mp3_bytes, "audio/mpeg")}
    data = {"model": MODEL, "customName": name, "text": ""}   # text 空:无逐字稿,zero-shot 仍可用
    r = httpx.post(f"{API}/uploads/audio/voice",
                   headers={"Authorization": f"Bearer {key}"}, data=data, files=files, timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_text": r.text[:200]}


def synth_with_uri(key: str, uri: str, text: str, out: Path) -> int:
    payload = {"model": MODEL, "input": text, "voice": uri,
               "response_format": "mp3", "sample_rate": 32000}
    r = httpx.post(f"{API}/audio/speech",
                   headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   json=payload, timeout=60)
    if r.status_code == 200:
        out.write_bytes(r.content)
        return len(r.content)
    return 0


def main():
    if len(sys.argv) < 2:
        print("用法:python clone_segments.py <audio_or_video> [seg_len=15] [test_text]"); sys.exit(1)
    src = Path(sys.argv[1])
    seg_len = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    test_text = sys.argv[3] if len(sys.argv) > 3 else TEST_TEXT
    if not src.is_file():
        print(f"错误:找不到 {src}"); sys.exit(1)
    key = load_key()
    if not key:
        print("错误:无 SILICONFLOW_API_KEY"); sys.exit(1)
    dur = probe_duration(src)
    outdir = src.parent / "clone_samples"
    outdir.mkdir(exist_ok=True)
    print(f"源:{src.name}  时长 {dur:.1f}s  段长 {seg_len}s(每段克隆<30s 限)")
    print(f"测试句:{test_text}")
    print("=" * 60)

    uris: dict = {}
    n = 0
    start = 0.0
    while start < dur:
        length = min(seg_len, dur - start)
        if length < MIN_SEG:
            print(f"[尾段] {int(start)}-{int(start + length)}s <{MIN_SEG}s 跳过")
            break
        n += 1
        label = f"seg{n}_{int(start)}-{int(start + length)}s"
        with tempfile.TemporaryDirectory() as td:
            seg_mp3 = Path(td) / "seg.mp3"
            if not normalize_segment(src, start, length, seg_mp3):
                print(f"[段{n}] {label} 切段/归一化失败"); start += seg_len; continue
            code, resp = upload_clone(key, seg_mp3.read_bytes(), label)
            if code != 200 or not isinstance(resp, dict) or not resp.get("uri"):
                print(f"[段{n}] {label} 克隆失败 HTTP {code}: {str(resp)[:150]}")
                start += seg_len
                continue
            uri = resp["uri"]
            sample = outdir / f"seg{n}.mp3"
            size = synth_with_uri(key, uri, test_text, sample)
            uris[label] = uri
            print(f"[段{n}] {label}  [OK] 样本 {size / 1024:.0f}KB -> {sample}")
        start += seg_len

    (outdir / "uris.json").write_text(json.dumps(uris, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 60)
    print(f"完成 {len(uris)} 段克隆。试听 {outdir}/seg*.mp3 选最像目标的段,")
    print(f"告诉我段号(如 seg3),我帮你把它设为当前音色(全 TTS 复用);不满意可删(uris.json 有全部 uri)。")


if __name__ == "__main__":
    main()
