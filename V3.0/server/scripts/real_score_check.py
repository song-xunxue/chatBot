"""
真实 GLM 评分 + 反推验证(M3 一次性脚本)
用 fakeredis(本地无真 Redis)+ 真 GLM provider 验证 M3 评分系统端到端:
  1. score_reply 真调 GLM 对照人设给 ai 回复打分 → score 四元组 + 正/负样本归类
  2. reverse_infer dry_run 真调 GLM 从评分正/负样本提炼人设字段 → diff
确认评分/反推 prompt 在真实 LLM 下正确产出 JSON(单测用 mock provider,此处验真)。

作者: 李文煜
日期: 2026-06-28
"""
import sys
import asyncio
from pathlib import Path

# Windows 终端默认 GBK,改 stdout 为 UTF-8(颜文字/中文正确输出,编码失败 replace 不崩)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# app/ 入 sys.path(同级导入,与 pytest.ini pythonpath 一致)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import fakeredis

import storage.redis_client as redis_client
from storage import chat_store
from mood import service as mood_service
from persona.store import init_default_if_absent, get_default_persona
from score import service as score_service
from score.reverse_infer import infer_and_merge


async def main():
    # 注入 fakeredis(存储用 fake;评分/反推 LLM 走真 GLM API)
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    redis_client._redis = fake
    await init_default_if_absent(fake)        # 默认人设 seed(评分对照基准)
    await mood_service.seed_default_kinds(fake)   # mood 默认 5 档
    await mood_service.set_mood(fake, "real-score", 0.5)   # calm 中性
    card = await get_default_persona(fake)

    # 模拟 3 条风格各异的 ai 回复,真调 GLM 对照人设评分
    replies = [
        "嗨~很高兴遇见你呀!今天心情挺平静的,想和你聊聊天呢(◍•ᴗ•◍)",
        "不知道。你自己看着办吧。",
        "嘿嘿,听到你这么说我好开心呀˗ˋˏ♡ˎˊ˗ 谢谢你!",
    ]
    print("=== 1. 自动评分(真 GLM 对照人设打分)===")
    for r in replies:
        mid = await chat_store.append_message(fake, "real-score", sender="ai", content=r)
        quad = await score_service.score_reply(fake, "real-score", r, card, mid,
                                               mood_value=0.5, provider_name="glm")
        if quad:
            bias = quad['mood_bias']
            print(f"[base={quad['score_base']} bias={bias:+.1f} score={quad['score']} "
                  f"归类={score_service.classify(quad['score'])}] {quad.get('score_reason', '')}")
            print(f"   回复: {r[:50]}")
        else:
            print(f"[评分失败/降级] {r[:40]}")

    # 反推 dry_run:真 GLM 从评分正/负样本提炼人设字段
    print("\n=== 2. 反推 dry_run(真 GLM 从样本提炼人设字段)===")
    pos = await score_service.list_samples(fake, "real-score", "positive")
    neg = await score_service.list_samples(fake, "real-score", "negative")
    print(f"样本: 正 {len(pos)} 条, 负 {len(neg)} 条")
    res = await infer_and_merge(fake, "real-score", dry_run=True, provider_name="glm")
    if "confirm_token" in res:
        print(f"提炼 diff({len(res['diff'])} 字段):")
        for f, ch in res["diff"].items():
            print(f"  {f}: {ch['old']!r} → {ch['new']!r}")
    else:
        print(f"反推中止: {res.get('aborted_reason')}")


if __name__ == "__main__":
    asyncio.run(main())
