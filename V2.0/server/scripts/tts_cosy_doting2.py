"""
CosyVoice2 溺爱强化(A 基础改,2026-08-07)
A 版反馈"语气/语速都平"。强化:语气词(呐嘛哦嗯呀)+密集[breath]气声停顿+[laughter]轻笑+
情感指令更强烈(气声呢喃/撒娇/轻颤)+短长句交错制造快慢起伏。两强化度对比。

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


def synth(text, emo, out, label):
    inp = f"{emo}<|endofprompt|>{text}"
    r = httpx.post(f"{API}/audio/speech", headers=auth, timeout=90,
                   json={"model": MODEL, "input": inp, "voice": f"{MODEL}:claire",
                         "response_format": "mp3", "sample_rate": 32000, "speed": 1.0})
    if r.status_code != 200:
        print(f"  {label} 失败 HTTP {r.status_code}: {r.text[:150]}"); return
    out.write_bytes(r.content)
    print(f"  {label} -> {out.name} ({len(r.content)/1024:.0f}KB)")


# A2:适度强化(A + 语气词 + breath/laughter + 更强情感)
EMO2 = "用极度宠溺、溺爱到快化掉的语气，气声呢喃着对最爱的人说话，带点撒娇；语速有起伏，温柔处气声拉长放慢、关键处加重，切忌平板地念"
T2 = "夫君呐……过来嘛。[breath]让我，靠着你一会儿……乖哦，什么也别想了。[laughter]外面太吵了，是不是？——没关系，有我在呢。嗯……你呀，只需要待在我身边，哪儿也不用去。因为——你是我一个人的呀。我最宝贝的……夫君。"

# A3:极致强化(密集气声 + 撒娇颤音 + 短长句交错,最大化起伏)
EMO3 = "用极致溺爱、撒娇、气声轻颤的语气，像贴着耳朵哄最爱的人；语速剧烈起伏，短句轻快、长句拖长气声、占有欲处放慢加重，带呼吸和轻笑"
T3 = "夫君……嗯？过来嘛。[breath][breath]乖——靠着我……[laughter]外面，太吵了对不对？没关系哦。嗯……有我呢。你呀……只需要待在我身边。哪儿——也不用去。因为……[breath]你是我一个人的呀。最宝贝的，夫君呐。"

print("=" * 50)
print("[A2] 适度强化(语气词+气声+撒娇)")
print(f"    指令:{EMO2}")
print(f"    文本:{T2}")
synth(T2, EMO2, OUT / "cosy_doting_A2.mp3", "A2")
print("[A3] 极致强化(密集气声+撒娇颤音+短长句交错)")
print(f"    指令:{EMO3}")
print(f"    文本:{T3}")
synth(T3, EMO3, OUT / "cosy_doting_A3.mp3", "A3")
print("=" * 50)
print("试听 E:/FFOutput/cosy_doting_A2.mp3 + cosy_doting_A3.mp3")
print("起伏/溺爱感强了吗?仍平的话——CosyVoice2 韵律是本质弱项,要真正抑扬顿挫得上 Azure(SSML prosody 逐句控)")
