"""
硅基流动 TTS API 实测(2026-08-04 TTS 调研)
验证 FunAudioLLM/CosyVoice2-0.5B 能否正常生成语音,记录格式/大小/延迟/音色可用性。
产物 tts_test_output.mp3 供人工试听质量(不入库 git;实测后可删)。

调用规格(https://api-docs.siliconflow.cn/docs/api/audio-speech-post):
  POST https://api.siliconflow.cn/v1/audio/speech
  header: Authorization: Bearer {key}
  body:   {model, input, voice, response_format, sample_rate, speed, stream}
  resp:   200 直接返回音频二进制(非 JSON);header x-siliconcloud-trace-id

作者: 李文煜
日期: 2026-08-04
"""
import sys
import time
from pathlib import Path

import httpx

# server/scripts 向上两级 = V2.0/ 项目根(含 .env)
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
API_URL = "https://api.siliconflow.cn/v1/audio/speech"
MODEL = "FunAudioLLM/CosyVoice2-0.5B"
OUT_PATH = Path(__file__).resolve().parent / "tts_test_output.mp3"


def load_key() -> str:
    """从 .env 读 SILICONFLOW_API_KEY(不硬编码,不打印完整值)"""
    if not ENV_PATH.is_file():
        return ""
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("SILICONFLOW_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def synth(key: str, text: str, voice: str, *, response_format: str = "mp3", sample_rate: int = 32000) -> dict:
    """单次合成,返回 {ok, status, latency, size_kb, content_type, trace_id, error}"""
    payload = {
        "model": MODEL,
        "input": text,
        "voice": voice,
        "response_format": response_format,
        "sample_rate": sample_rate,
        "speed": 1.0,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    t0 = time.time()
    try:
        # 非流式:整包拿二进制(实测够用;流式 stream=true 适合长文本/低首字延迟)
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(API_URL, headers=headers, json=payload)
    except Exception as e:
        return {"ok": False, "error": f"请求异常: {e}", "latency": round(time.time() - t0, 2)}
    latency = round(time.time() - t0, 2)
    info = {
        "status": resp.status_code,
        "latency": latency,
        "content_type": resp.headers.get("content-type", ""),
        "trace_id": resp.headers.get("x-siliconcloud-trace-id", ""),
        "size_kb": round(len(resp.content) / 1024, 1),
    }
    if resp.status_code != 200:
        info["ok"] = False
        info["error"] = resp.text[:300]
        return info
    info["ok"] = True
    info["bytes"] = resp.content
    return info


def main():
    key = load_key()
    if not key:
        print("错误:V2.0/.env 无 SILICONFLOW_API_KEY,无法实测"); sys.exit(1)
    print(f"key 已加载(前6位 {key[:6]}...)"); print("=" * 60)

    # 测试1:CosyVoice2 自然语言指令 + 韵律标记(拟人化真实场景)
    text1 = "你能用温柔开心的语气说吗?<|endofprompt|>夫君,今天辛苦啦,早点休息哦。[laughter]"
    voice1 = f"{MODEL}:alex"
    print(f"[测1] 指令+韵律标记  voice=alex")
    r1 = synth(key, text1, voice1)
    print(f"  HTTP {r1.get('status')}  耗时 {r1.get('latency')}s  大小 {r1.get('size_kb')} KB")
    print(f"  Content-Type {r1.get('content_type')}  trace {r1.get('trace_id')}")
    if r1["ok"]:
        OUT_PATH.write_bytes(r1["bytes"])
        print(f"  已保存试听: {OUT_PATH}")
    else:
        print(f"  失败: {r1.get('error')}")

    print("=" * 60)
    # 测试2:换音色 + 纯文本(无指令,验证其他预设音色 + 基础可用)
    text2 = "嗯,我也刚醒,今天天气真好,想出去走走。"
    voice2 = f"{MODEL}:benjamin"
    print(f"[测2] 纯文本  voice=benjamin(验证另一音色)")
    r2 = synth(key, text2, voice2)
    print(f"  HTTP {r2.get('status')}  耗时 {r2.get('latency')}s  大小 {r2.get('size_kb')} KB")
    if not r2["ok"]:
        print(f"  失败: {r2.get('error')}")

    print("=" * 60)
    ok_count = sum(1 for r in (r1, r2) if r.get("ok"))
    print(f"总结:{ok_count}/2 成功  模型 {MODEL}")
    if ok_count == 2:
        print("实测结论:硅基流动 CosyVoice2-0.5B TTS 可用,多音色 + 指令/韵律标记均正常")
    sys.exit(0 if ok_count else 3)


if __name__ == "__main__":
    main()
