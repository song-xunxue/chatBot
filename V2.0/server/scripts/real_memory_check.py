"""
真实 GLM 记忆巩固 + BM25 检索验证(M4 一次性脚本)
用 fakeredis + 真 GLM 验证 M4 记忆融合端到端:
  1. encoder.extract_facts 真调 GLM 从对话抽事实 → long-term
  2. consolidate_sleep 真调 GLM 从 episodic 摘要巩固为长期事实
  3. coordinator.retrieve 真 BM25 召回(关加权随机,确定性便于观察)
单测用 mock provider,此处验真 GLM JSON 输出 + BM25 召回相关性。

作者: 李文煜
日期: 2026-06-28
"""
import sys
import asyncio
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import fakeredis

import storage.redis_client as redis_client
from core.config import settings
from memory import store, encoder
from memory.models import EpisodicEntry
from memory.coordinator import MemoryCoordinator
from memory.consolidation import consolidate_sleep
from llm.registry import get_provider
from persona.store import init_default_if_absent
from mood import service as mood_service


async def main():
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    redis_client._redis = fake
    await init_default_if_absent(fake)
    await mood_service.seed_default_kinds(fake)
    settings.memory_weighted_sample = False    # 确定性召回,便于观察 BM25 相关性
    provider = get_provider("glm")
    coord = MemoryCoordinator(fake, llm_provider=provider)

    print("=== 1. extract_facts(真 GLM 从对话抽事实 → long-term)===")
    user_text = "我叫林晓,今年大二,养了一只橘猫叫橘子。我平时喜欢周末去爬山,最近在学吉他。"
    reply = "你好林晓!橘子一定很可爱~爬山和吉他都是很好的爱好呢。"
    facts = await encoder.extract_facts(user_text, reply, provider, "")
    existing = await store.get_all_long_term(fake, "u1")
    for f in facts:
        await coord._upsert_fact_dedup("u1", f, existing)
    print(f"抽取 {len(facts)} 条事实:")
    for m in await store.get_all_long_term(fake, "u1"):
        print(f"  [{m.category.value} imp={m.importance:.1f}] {m.content}")

    print("\n=== 2. consolidate_sleep(真 GLM 从 episodic 摘要巩固)===")
    for i, s in enumerate(["用户提到自己叫林晓,大二学生",
                           "用户聊到橘猫橘子和爬山爱好",
                           "用户最近开始学吉他"]):
        await store.append_episodic(fake, "u1", EpisodicEntry(
            id=f"e{i}", summary=s, span_start_ts=1, span_end_ts=2, created_ts=(i + 1) * 1000))
    res = await consolidate_sleep(fake, "u1", provider, "", coordinator=coord)
    print(f"巩固结果: 新增 {res['facts_added']} 条事实, 清理 {res['episodic_pruned']} 条 episodic")

    print("\n=== 3. retrieve BM25 召回 ===")
    for q in ["猫", "爱好", "吉他", "学校"]:
        rr = await coord.retrieve("u1", q, top_k=3)
        contents = [m.content[:25] for m in rr.long_term]
        print(f"  query='{q}' → {contents}")


if __name__ == "__main__":
    asyncio.run(main())
