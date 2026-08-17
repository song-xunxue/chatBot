"""
真实 GLM 回复验证(M2 一次性脚本,不入库)
用 fakeredis(本地无真 Redis)+ 真 GLM provider 跑通 pipeline 全链路,打印 LLM 真实回复。
验证:QQ 消息 → 防抖(略)→ pipeline(persona/mood/记忆/LLM)→ 回复。

作者: 李文煜
日期: 2026-06-27
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
from mood import service
from persona.store import init_default_if_absent
from pipeline.context import MessageContext
from pipeline.runner import run_stream


async def main():
    # 注入 fakeredis(本地无真 Redis;真实回复只需 LLM 走真 API,存储用 fake 即可)
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    redis_client._redis = fake
    await init_default_if_absent(fake)       # 默认人设 seed
    await service.seed_default_kinds(fake)   # mood 默认 5 档

    user_text = "你好呀,介绍一下你自己,顺便说说你今天心情怎么样"
    print(f"[user] {user_text}")
    print("[ai] ", end="", flush=True)
    ctx = MessageContext(object_id="real-test", user_text=user_text, provider_name="glm")
    async for token in run_stream(ctx):
        print(token, end="", flush=True)
    print()
    print(f"\n--- 心情档位: {ctx.plugin_meta.get('mood')} {ctx.plugin_meta.get('mood_kaomoji')}")
    hist = await chat_store.get_history(fake, "real-test")
    print(f"--- 落库历史(block): {[(m.role, m.content[:30] + ('...' if len(m.content) > 30 else '')) for m in hist]}")


if __name__ == "__main__":
    asyncio.run(main())
