"""
记忆睡眠巩固(M4,借鉴 angel_memory 睡眠巩固机制)
consolidate_sleep:把高 importance 的情景记忆摘要提炼为长期事实(经 coordinator 去重合并)+
清理冗余 episodic(超 memory_episodic_keep 删最旧)。

定期触发(由 coordinator.forget_tick 整合,复用遗忘批处理周期,不新增 loop)。
无 LLM 时只做 episodic 清理(降级)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M4 新建 consolidation:consolidate_sleep(episodic→long-term 巩固 + 冗余清理)
"""
import logging

from memory import store, encoder

logger = logging.getLogger(__name__)


async def consolidate_sleep(redis, object_id: str, llm, model: str,
                            coordinator, *, importance_threshold: float | None = None) -> dict:
    """睡眠巩固单对象(借鉴 angel_memory):
    1. 取全部 episodic 摘要 → LLM 提炼长期事实(consolidate_facts)
    2. importance 达阈值的 fact 经 coordinator._upsert_fact_dedup 去重合并入 long-term
    3. episodic 超 memory_episodic_keep 清理最旧(控增长)
    返回 {facts_added, episodic_pruned};调用方须持 coordinator._lock(oid)。
    无 LLM 时跳过提炼,仍做 episodic 清理(降级)。"""
    from core.config import settings
    threshold = (settings.memory_consolidate_importance
                 if importance_threshold is None else importance_threshold)
    facts_added = 0
    episodic_pruned = 0
    try:
        epis = await store.get_episodic(redis, object_id, limit=50)
        if epis and llm:
            summaries = [e.summary for e in epis if e.summary]
            if summaries:
                facts = await encoder.consolidate_facts(summaries, llm, model)
                existing = await store.get_all_long_term(redis, object_id)
                for f in facts:
                    if float(f.get("importance", 0)) >= threshold:
                        await coordinator._upsert_fact_dedup(object_id, f, existing)
                        facts_added += 1
        # episodic 冗余清理(无论是否有 LLM 都执行)
        keep = settings.memory_episodic_keep
        if keep > 0:
            episodic_pruned = await store.prune_oldest_episodic(redis, object_id, keep)
    except Exception as e:
        logger.warning("consolidate_sleep 失败 oid=%s: %s", object_id, e)
    if facts_added or episodic_pruned:
        logger.info("consolidate oid=%s facts_added=%d episodic_pruned=%d",
                    object_id, facts_added, episodic_pruned)
    return {"facts_added": facts_added, "episodic_pruned": episodic_pruned}
