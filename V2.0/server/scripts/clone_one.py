"""
单段短素材(<30s)直接克隆(M-tts 自定义音色,2026-08-07)
适合 8-10s 干净单人讲话素材:上传→克隆 uri→合成测试句→存样本试听。
长素材(>30s)用 clone_segments.py 切段;本脚本用于已截好的短素材。

用法:python clone_one.py <audio_or_video> [test_text]
产物:同级 <name>_sample.mp3(克隆合成的测试句,试听)+ last_clone_uri.txt(uri,设当前用)

作者: 李文煜
日期: 2026-08-07
"""
import re
import sys
import subprocess
import tempfile
from pathlib import Path

import httpx

ENV = Path(__file__).resolve().parents[2] / ".env"
API = "https://api.siliconflow.cn/v1"
MODEL = "FunAudioLLM/CosyVoice2-0.5B"
TEST_TEXT = "夫君，今天辛苦啦，早点休息哦。"


def load_key() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("SILICONFLOW_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main():
    if len(sys.argv) < 2:
        print("用法:python clone_one.py <audio_or_video> [test_text]"); sys.exit(1)
    src = Path(sys.argv[1])
    text = sys.argv[2] if len(sys.argv) > 2 else TEST_TEXT
    if not src.is_file():
        print(f"错误:找不到 {src}"); sys.exit(1)
    key = load_key()
    if not key:
        print("错误:无 SILICONFLOW_API_KEY"); sys.exit(1)
    auth = {"Authorization": "Bearer " + key}
    print(f"源:{src.name}  测试句:{text}")

    # 视频则提音频;音频直接用
    raw = src.read_bytes()
    if src.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v"):
        FFM = r"C:\Users\26904\anaconda3\envs\mychat\Library\bin\ffmpeg.exe"
        with tempfile.TemporaryDirectory() as td:
            v = Path(td) / "v.in"; a = Path(td) / "a.mp3"
            v.write_bytes(raw)
            subprocess.run([FFM, "-y", "-i", str(v), "-vn", "-ac", "1", "-ar", "16000",
                            "-c:a", "libmp3lame", "-b:a", "192k", str(a)], capture_output=True)
            raw = a.read_bytes()

    # 上传克隆(customName 仅允许字母/数字/_/-,清洗文件名)
    cname = re.sub(r"[^A-Za-z0-9_-]", "", src.stem)[:20] or "voice"
    r = httpx.post(f"{API}/uploads/audio/voice", headers=auth, timeout=60,
                   data={"model": MODEL, "customName": cname, "text": ""},
                   files={"file": ("ref.mp3", raw, "audio/mpeg")})
    print("upload", r.status_code, r.text[:150])
    if r.status_code == 403:
        print("403:账号未实名"); sys.exit(2)
    uri = r.json().get("uri") if r.status_code == 200 else None
    if not uri:
        print("未拿到 uri"); sys.exit(3)
    print("uri:", uri)

    # 合成测试句
    r2 = httpx.post(f"{API}/audio/speech", timeout=60,
                    headers={**auth, "Content-Type": "application/json"},
                    json={"model": MODEL, "input": text, "voice": uri,
                          "response_format": "mp3", "sample_rate": 32000})
    if r2.status_code != 200:
        print(f"synth 失败 HTTP {r2.status_code}: {r2.text[:200]}")
        print("(若 500/50507:素材可能有 BGM/混响/多人,试 demucs 去BGM 或换更干净素材)")
        sys.exit(4)
    out = src.parent / f"{src.stem}_sample.mp3"
    out.write_bytes(r2.content)
    (src.parent / "last_clone_uri.txt").write_text(uri, encoding="utf-8")
    print(f"[OK] synth {len(r2.content)/1024:.0f}KB -> {out}")
    print(f"uri 已存 {src.parent}/last_clone_uri.txt(设当前音色用)")
    print("试听样本,满意告诉我 -> 我帮你设为当前音色(全 TTS 复用)")


if __name__ == "__main__":
    main()
