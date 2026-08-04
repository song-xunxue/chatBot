"""
硅基流动声音克隆链路验证(M-tts 自定义音色调研,2026-08-04)
验证:① Upload a Voice 上传参考音频拿 uri ② 用克隆 uri 合成 ③ List/Delete 管理。
排除最大风险(账号实名认证 → 否则 403)+ 验证现有 _full_voice 含冒号透传克隆 uri 的接入可行性。

用已有 tts_test_output.mp3(alex 音色)作测试参考音频(仅验证链路,非目标音色)。
产物 clone_test.mp3 试听;测试音色最后删除清理。

作者: 李文煜
日期: 2026-08-04
"""
import sys
from pathlib import Path

import httpx

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
API = "https://api.siliconflow.cn/v1"
MODEL = "FunAudioLLM/CosyVoice2-0.5B"
REF_MP3 = Path(__file__).resolve().parent / "tts_test_output.mp3"   # 已有测试音频
OUT = Path(__file__).resolve().parent / "clone_test.mp3"
REF_TEXT = "夫君，今天辛苦啦，早点休息哦"   # 该 mp3 实际说的话(上传用于对齐)
SYNTH_TEXT = "这是用克隆音色合成的一句话，听听效果。"


def load_key() -> str:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("SILICONFLOW_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main():
    key = load_key()
    if not key:
        print("错误:无 SILICONFLOW_API_KEY"); sys.exit(1)
    if not REF_MP3.is_file():
        print(f"错误:缺 {REF_MP3}(先跑 real_tts_check.py 生成)"); sys.exit(1)
    headers = {"Authorization": f"Bearer {key}"}
    print(f"key 已加载(前6位 {key[:6]}...)"); print("=" * 60)

    # 1. 上传参考音频(multipart)→ 拿克隆 uri
    print("[1/4] 上传参考音频(Upload a Voice)")
    with open(REF_MP3, "rb") as f:
        files = {"file": ("ref.mp3", f, "audio/mpeg")}
        data = {"model": MODEL, "customName": "test-clone-check", "text": REF_TEXT}
        r = httpx.post(f"{API}/uploads/audio/voice", headers=headers, data=data, files=files, timeout=60)
    print(f"  HTTP {r.status_code}")
    if r.status_code == 403:
        print(f"  403 拦截 → 账号未实名认证(克隆音色硬门槛): {r.text[:200]}"); sys.exit(2)
    if r.status_code != 200:
        print(f"  上传失败: {r.text[:300]}"); sys.exit(3)
    uri = r.json().get("uri")
    print(f"  克隆 uri: {uri}")
    if not uri:
        print(f"  返回无 uri: {r.text[:200]}"); sys.exit(4)

    # 2. 用克隆 uri 合成(验证 _full_voice 含冒号透传逻辑:uri 含冒号→原样作 voice)
    print("[2/4] 用克隆 uri 合成新文本")
    payload = {"model": MODEL, "input": SYNTH_TEXT, "voice": uri,
               "response_format": "mp3", "sample_rate": 32000}
    r2 = httpx.post(f"{API}/audio/speech",
                    headers={**headers, "Content-Type": "application/json"},
                    json=payload, timeout=60)
    print(f"  HTTP {r2.status_code}  大小 {len(r2.content)/1024:.1f} KB")
    if r2.status_code == 200:
        OUT.write_bytes(r2.content)
        print(f"  克隆合成已保存试听: {OUT}")
    else:
        print(f"  合成失败: {r2.text[:300]}")

    # 3. 列已克隆音色
    print("[3/4] 列已克隆音色(List Voices)")
    r3 = httpx.get(f"{API}/audio/voice/list", headers=headers, timeout=30)
    print(f"  HTTP {r3.status_code}: {r3.text[:200]}")

    # 4. 清理:删除测试音色
    print("[4/4] 删除测试音色(清理)")
    r4 = httpx.post(f"{API}/audio/voice/deletions", headers=headers,
                    json={"uri": uri}, timeout=30)
    print(f"  HTTP {r4.status_code}: {r4.text[:150]}")

    print("=" * 60)
    ok = r.status_code == 200 and r2.status_code == 200
    print("结论:" + ("PASS - 克隆链路通,账号已实名,uri 合成可用,可接入面板" if ok else "FAIL - 见上方错误"))


if __name__ == "__main__":
    main()
