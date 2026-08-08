"""
GAG(api_v2 9880) API 测试(M-tts GPT-SoVITS 接入,2026-08-08)
用清浔预设参数(dania 模型 + 参考音频)合成一句,验证 API 链路 + 音色。
服务端已加载 dania(GAG GUI 操作过),直接 /tts 复用。

作者: 李文煜
日期: 2026-08-08
"""
import httpx
from pathlib import Path

API = "http://127.0.0.1:9880"
# 清浔预设参数(从 GAG_config.json 读)
GPT_MODEL = "GPT_weights_v2ProPlus\\dania.ckpt"
SOVITS_MODEL = "SoVITS_weights_v2ProPlus\\dania.pth"
REF = "E:/GPT-SoVITS/output/slicer_opt/output.wav_0009342720_0009558400.wav"
PROMPT_TEXT = "怎么啊？如果有你在也不放心，那就干脆给我也装个限制器或者炸弹喽。"
TEXT = "夫君，今天辛苦啦，早点休息哦。"
OUT = Path("E:/FFOutput/gag_test.wav")

# 确认参考音频在
if not Path(REF).is_file():
    print(f"错误:参考音频不存在 {REF}"); raise SystemExit(1)
print(f"参考音频 OK: {Path(REF).name} ({Path(REF).stat().st_size//1024}KB)")

# 先显式加载清浔 dania 模型(确保音色对,幂等)
print("加载清浔 dania 模型...")
r0 = httpx.get(f"{API}/set_gpt_weights", params={"weights_path": GPT_MODEL}, timeout=30)
print(f"  set_gpt_weights: {r0.status_code}")
r1 = httpx.get(f"{API}/set_sovits_weights", params={"weights_path": SOVITS_MODEL}, timeout=30)
print(f"  set_sovits_weights: {r1.status_code}")

# 用清浔预设参数合成
payload = {
    "text": TEXT, "text_lang": "all_zh",
    "ref_audio_path": REF, "prompt_text": PROMPT_TEXT, "prompt_lang": "all_zh",
    "top_k": 5, "top_p": 1.0, "temperature": 1.0,
    "text_split_method": "cut1", "batch_size": 4, "batch_threshold": 0.75,
    "split_bucket": False, "return_fragment": False,
    "speed_factor": 1.0, "streaming_mode": False, "seed": -1,
    "parallel_infer": True, "repetition_penalty": 1.35,
    "media_type": "wav",
}
print(f"\n调 POST /tts 合成:{TEXT}")
r = httpx.post(f"{API}/tts", json=payload, timeout=120)
print(f"HTTP {r.status_code}  大小 {len(r.content)/1024:.1f}KB")
if r.status_code == 200:
    OUT.write_bytes(r.content)
    print(f"[OK] 已存 {OUT}  试听看音色是否清浔(dania)")
else:
    print(f"失败: {r.text[:300]}")
