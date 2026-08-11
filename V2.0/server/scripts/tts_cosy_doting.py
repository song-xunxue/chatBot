"""
CosyVoice2 溺爱沉静占有向(常速,2026-08-07)
针对"语速无变化"反馈:文本密集停顿(……/——/，/。/[breath])强制节奏起伏 + 指令要求抑扬顿挫。
两版停顿密度对比,常速 speed 1.0。

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

EMOTION = "用沉静、溺爱、平静中带着占有欲的语气，像低声呢喃着对最爱的人说话；语速要有抑扬顿挫和起伏，该强调的地方放慢、轻声处拉长，不要一条直线地念"


def synth(text, out, label):
    inp = f"{EMOTION}<|endofprompt|>{text}"
    payload = {"model": MODEL, "input": inp, "voice": f"{MODEL}:claire",
               "response_format": "mp3", "sample_rate": 32000, "speed": 1.0}
    r = httpx.post(f"{API}/audio/speech", headers=auth, json=payload, timeout=90)
    if r.status_code != 200:
        print(f"  {label} 失败 HTTP {r.status_code}: {r.text[:150]}")
        return
    out.write_bytes(r.content)
    print(f"  {label} -> {out.name} ({len(r.content)/1024:.0f}KB)")


# 版本1:中等停顿(自然溺爱向,断句 + 呼吸)
T1 = "夫君……过来。——让我，靠着你一会儿。乖，什么也别想。[breath]外面太吵了是不是？没关系，有我在呢。你呀，只需要待在我身边，哪儿也不用去……因为——你是我一个人的。我最宝贝的，夫君。"
# 版本2:密集停顿(更多 ……/—— 强制更长停顿,节奏起伏更明显)
T2 = "夫君……过来。乖——让我，靠着你……什么，也别想了。[breath]外面……是不是很吵？没关系。有我呢。你呀……只需要，待在我身边——哪儿，也不用去。因为……你是我一个人的。最宝贝的——夫君。"

print(f"情感指令:{EMOTION}\n" + "=" * 50)
print("[A] 中等停顿版")
print(f"    {T1}")
synth(T1, OUT / "cosy_doting_A.mp3", "A")
print("[B] 密集停顿版(节奏起伏更明显)")
print(f"    {T2}")
synth(T2, OUT / "cosy_doting_B.mp3", "B")
print("=" * 50)
print("试听 E:/FFOutput/cosy_doting_A.mp3 + cosy_doting_B.mp3(均常速)")
print("语速有变化了吗?哪个更接近?还要更溺爱/更沉静/换文本继续调")
