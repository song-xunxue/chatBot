"""
CosyVoice2 预设音色探测(2026-08-04 M-tts 设计)
挨个试候选预设音色,拿 API 返回 200 的确切清单(作面板下拉选项)。
另测情感指令机制(<|endofprompt|>)与自定义克隆 references 入口是否可用。

端点 POST https://api.siliconflow.cn/v1/audio/speech  voice=FunAudioLLM/CosyVoice2-0.5B:{name}

作者: 李文煜
日期: 2026-08-04
"""
import sys
from pathlib import Path

import httpx

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
API_URL = "https://api.siliconflow.cn/v1/audio/speech"
MODEL = "FunAudioLLM/CosyVoice2-0.5B"

# 候选预设音色(SiliconFlow CosyVoice2 常见集,API 会拒绝无效名)
CANDIDATES = [
    "alex", "anna", "bella", "benjamin", "charles", "claire", "daniel", "diana",
    "ian", "jane", "jesse", "john", "matilda", "mia", "noah", "olivia",
    "sam", "sarah", "steve", "tony", "matthew", "nancy", "chelsie", "joseph",
]


def load_key() -> str:
    if not ENV_PATH.is_file():
        return ""
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("SILICONFLOW_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def probe(key: str, voice_full: str, text: str = "你好呀。") -> tuple[int, str]:
    payload = {"model": MODEL, "input": text, "voice": voice_full,
               "response_format": "mp3", "sample_rate": 32000}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(API_URL, headers=headers, json=payload)
    except Exception as e:
        return -1, str(e)
    if r.status_code == 200:
        return 200, f"{len(r.content)/1024:.0f}KB"
    # 提取错误关键信息(不打印全文)
    msg = r.text[:160].replace("\n", " ")
    return r.status_code, msg


def main():
    key = load_key()
    if not key:
        print("错误:无 SILICONFLOW_API_KEY"); sys.exit(1)
    print(f"探测 CosyVoice2-0.5B 预设音色(共 {len(CANDIDATES)} 候选)\n" + "=" * 50)

    ok = []
    for name in CANDIDATES:
        code, info = probe(key, f"{MODEL}:{name}")
        flag = "OK " if code == 200 else "   "
        print(f"  {flag} {name:10s} -> {code}  {info}")
        if code == 200:
            ok.append(name)

    print("=" * 50)
    print(f"可用预设音色({len(ok)}/{len(CANDIDATES)}):{ok}")
    sys.exit(0)


if __name__ == "__main__":
    main()
