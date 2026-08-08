"""
GPTSoVitsProvider 真实端到端验证(M-tts GPT-SoVITS 接入,2026-08-08)
走 get_tts("gptsovits") → GPTSoVitsProvider(读 .env 的 GPTSOVITS_* 配置)→ 调真服务 9880 合成。
验证整条 provider 链路(非 mock):config 读取 + _ensure_weights + /tts + 返 wav。

作者: 李文煜
日期: 2026-08-08
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))  # server/app 入 sys.path

from modality.tts import get_tts


async def main():
    p = get_tts("gptsovits")
    print(f"provider={p.name}  api={p.api_base}")
    print(f"gpt_model={p.gpt_model}")
    print(f"sovits_model={p.sovits_model}")
    print(f"ref_audio={p.ref_audio}")
    print(f"prompt_text={p.prompt_text}")
    if not p.ref_audio:
        print("错误:.env 未配 GPTSOVITS_REF_AUDIO"); return
    print("合成中(GPT-SoVITS 服务端处理)...")
    wav = await p.synthesize("夫君，今天辛苦啦，早点休息哦。", voice="ignored", speed=1.0)
    out = Path("E:/FFOutput/gag_provider_test.wav")
    out.write_bytes(wav)
    print(f"[OK] {len(wav)/1024:.1f}KB -> {out}")
    print("试听确认音色 = 清浔(dana)。OK 则 provider 链路通,可切 TTS_PROVIDER=gptsovits 上线")


if __name__ == "__main__":
    asyncio.run(main())
