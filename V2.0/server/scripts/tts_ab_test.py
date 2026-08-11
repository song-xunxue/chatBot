"""
TTS A/B 对比(M-tts 升级调研,2026-08-07)
用 CosyVoice2-0.5B 和 fnlp/MOSS-TTSD-v0.5 各合成同一句(claire 音色),存两个 mp3 试听对比。
MOSS-TTSD 不认 <|endofprompt|>(会读出),故 emotion 注入只对 CosyVoice2 用。

产物 /e/FFOutput/ab_cosyvoice.mp3 + ab_moss.mp3

作者: 李文煜
日期: 2026-08-07
"""
import httpx
from pathlib import Path

ENV = Path(__file__).resolve().parents[2] / ".env"
key = next((l.split("=", 1)[1].strip().strip("'\"") for l in ENV.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("SILICONFLOW_API_KEY=")), "")
API = "https://api.siliconflow.cn/v1"
TEXT = "夫君，今天辛苦啦，早点休息哦。"
OUT = Path("E:/FFOutput")
auth = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}


def synth(model, voice, text, out):
    payload = {"model": model, "input": text, "voice": voice,
               "response_format": "mp3", "sample_rate": 32000}
    r = httpx.post(f"{API}/audio/speech", headers=auth, json=payload, timeout=60)
    if r.status_code != 200:
        print(f"  {model} 失败 HTTP {r.status_code}: {r.text[:150]}")
        return False
    out.write_bytes(r.content)
    print(f"  {model} -> {out.name} ({len(r.content)/1024:.0f}KB)")
    return True


print(f"测试句:{TEXT}\n" + "=" * 50)
# A: CosyVoice2(带情感指令,模拟实际用时的温柔撒娇语气)
cosy_inp = "你能用温柔撒娇的语气说吗?<|endofprompt|>" + TEXT
print("[A] CosyVoice2-0.5B + 情感指令(温柔撒娇)")
synth("FunAudioLLM/CosyVoice2-0.5B", "FunAudioLLM/CosyVoice2-0.5B:claire", cosy_inp, OUT / "ab_cosyvoice.mp3")
# B: MOSS-TTSD(不注情感指令,纯文本,靠模型自理解)
print("[B] fnlp/MOSS-TTSD-v0.5(纯文本,模型自理解情感)")
synth("fnlp/MOSS-TTSD-v0.5", "fnlp/MOSS-TTSD-v0.5:claire", TEXT, OUT / "ab_moss.mp3")
print("=" * 50)
print("试听 E:/FFOutput/ab_cosyvoice.mp3 vs ab_moss.mp3")
print("MOSS 明显更温柔有感情 -> 告诉我,我把 tts_model 切到 MOSS(改一行+emotion分支)")
print("差不多或更差 -> 直接上 Azure 晓晓(确定更温柔)")
