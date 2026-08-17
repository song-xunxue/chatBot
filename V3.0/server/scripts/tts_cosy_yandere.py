"""
CosyVoice2 病娇沉溺长样本(M-tts 试听,2026-08-07)
平静中带沉溺+微病娇语气,~15s 文本,情感指令+韵律标记,两个语速变体试听。

作者: 李文煜
日期: 2026-08-07
"""
import httpx
from pathlib import Path

ENV = Path(__file__).resolve().parents[2] / ".env"
key = next((l.split("=", 1)[1].strip().strip("'\"") for l in ENV.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("SILICONFLOW_API_KEY=")), "")
API = "https://api.siliconflow.cn/v1"
MODEL = "FunAudioLLM/CosyVoice2-0.5B"
OUT = Path("E:/FFOutput")
auth = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

# 病娇沉溺向长文本(~70字 ≈ 15s),平静+沉溺+微占有欲;[breath]/[laughter] 增病娇感
TEXT = "夫君……你今天回来得好晚呀。[breath]是不是，又在外面偷偷看了谁呢？没关系的哦，我不会生气的。[breath]因为不管怎样，你最后都会回到我身边，对吧？你是我一个人的，[laughter]永远，只能看着我呢。"
# 情感指令:平静中带沉溺+微病娇占有欲
EMOTION = "用平静、沉溺、又带着点病娇占有欲和黏人的语气说"


def synth(speed, out):
    inp = f"{EMOTION}<|endofprompt|>{TEXT}"
    payload = {"model": MODEL, "input": inp, "voice": f"{MODEL}:claire",
               "response_format": "mp3", "sample_rate": 32000, "speed": speed}
    r = httpx.post(f"{API}/audio/speech", headers=auth, json=payload, timeout=90)
    if r.status_code != 200:
        print(f"  speed {speed} 失败 HTTP {r.status_code}: {r.text[:150]}")
        return
    out.write_bytes(r.content)
    print(f"  speed {speed} -> {out.name} ({len(r.content)/1024:.0f}KB)")


print(f"情感指令:{EMOTION}")
print(f"文本:{TEXT}\n" + "=" * 50)
print("[1] 语速 1.0(常速)")
synth(1.0, OUT / "cosy_yandere_1.0.mp3")
print("[2] 语速 0.88(更慢更沉溺)")
synth(0.88, OUT / "cosy_yandere_0.88.mp3")
print("=" * 50)
print("试听 E:/FFOutput/cosy_yandere_1.0.mp3 + cosy_yandere_0.88.mp3")
print("告诉我:哪个更接近你要的'平静沉溺微病娇';或调整方向(更病娇/更沉溺/换文本/换音色)")
