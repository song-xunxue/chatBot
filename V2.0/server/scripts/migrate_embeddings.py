"""
迁移脚本:给已有长期记忆批量补 embedding 向量(2026-07-07 记忆优化阶段1)。
线上部署后跑一次,把存量 long-term 记忆全部向量化(供向量检索/语义去重用)。
幂等:已有 vec 的跳过。后续新记忆由 coordinator 写入时自动 embed,无需再跑。

用法(服务器 ~/ChatBot-V2/server 下,容器内或本地 conda mychat):
  python -m scripts.migrate_embeddings
  或  docker exec mychat-server-v2 python -m scripts.migrate_embeddings

作者: 李文煜
日期: 2026-07-07
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")


async def migrate() -> None:
    """扫描全部对象的 long-term 记忆,对无 vec 的批量 embed + 存"""
    from core.config import settings
    from llm.embedding import get_embedding_provider
    from memory import store
    from storage.redis_client import get_redis

    redis = await get_redis()
    provider = get_embedding_provider()
    if provider is None:
        print("未配置 embedding provider(memory_embedding_provider 或 glm_api_key),退出")
        return

    oids = await store.list_objects(redis)
    print(f"扫描 {len(oids)} 个对象,provider={provider.name} model={settings.memory_embedding_model}")
    total = 0
    for oid in oids:
        items = await store.get_all_long_term(redis, oid)
        if not items:
            continue
        vec_map = await store.get_vecs_bulk(redis, oid, [m.id for m in items])
        missing = [m for m in items if m.id not in vec_map]
        if not missing:
            continue
        # 批量 embed(provider 内部已分批处理超限)
        vecs = await provider.embed([m.content for m in missing], settings.memory_embedding_model)
        added = 0
        for m, v in zip(missing, vecs):
            if v:
                await store.set_vec(redis, oid, m.id, v)
                added += 1
        total += added
        print(f"  oid={oid[:24]}... 记忆 {len(items)} 条,补向量 {added} 条")
    print(f"完成:共补 {total} 条向量")


if __name__ == "__main__":
    asyncio.run(migrate())
