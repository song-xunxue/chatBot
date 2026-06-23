"""
记忆协调器 MemoryCoordinator
串联检索→组装→编码→遗忘，服务端常驻单例，对外唯一记忆入口。
M3.3 retrieve/render；M3.4 on_turn_complete（编码）；M3.5 forget_tick/手动遗忘。
M3-review 修正：per-oid 锁（RMW 一致性）、上限淘汰+物理清理、单例双检锁+初始化降级、
  事实去重归一化+缓存复用、负样本 pending、span_start_ts、Task 强引用由 stages 持有。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.3 创建 retrieve + render + 常驻单例
  2. M3.4 新增 on_turn_complete 编码（Episodic 摘要/反思 + Long-term 事实抽取去重合并）
  3. M3.5 新增 forget_tick/手动遗忘/恢复/批量遗忘
  4. M3-review 修正：per-oid asyncio.Lock 串行化 RMW；_enforce_max_facts 上限淘汰；
     forget_tick 补上限淘汰+物理清理；单例双检锁+初始化降级；record_negative_feedback；
     事实去重精确归一化短路 + existing 缓存复用；span_start_ts 用 ctx.created_ts
"""
import asyncio
import logging
import re
import time
import uuid

from redis.asyncio import Redis

from memory import store, encoder
from memory.models import RecallResult, ForgetConfig, EpisodicEntry, MemoryItem, Category
from memory.retriever import KeywordRetriever, _tokenize
from memory.forgetting import should_forget, retain_score

logger = logging.getLogger(__name__)

# 去重相似度阈值（关键词 Jaccard），超过则视为重复事实做合并
_DEDUP_THRESHOLD = 0.3


def _normalize(s: str) -> str:
    """归一化：去标点与空白，便于精确相等判定"""
    return re.sub(r"\s+|[^一-龥a-zA-Z0-9]", "", (s or "").lower())


def _similar(a: str, b: str, threshold: float = _DEDUP_THRESHOLD) -> bool:
    """事实去重：先精确归一化相等判定，否则关键词 Jaccard（首版，零依赖）"""
    if _normalize(a) == _normalize(b):
        return True
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


class MemoryCoordinator:
    """记忆协调器：检索→组装→编码→遗忘的唯一入口，服务端常驻"""

    def __init__(self, redis: Redis | None, llm_provider=None, cfg: ForgetConfig | None = None):
        self.redis = redis
        self.llm = llm_provider  # 编码用 LLM，None 时降级
        self.cfg = cfg or ForgetConfig()
        self.retriever = KeywordRetriever()
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, oid: str) -> asyncio.Lock:
        """per-object 锁：串行化同一对象的读-改-写，避免 access_count/去重并发覆盖"""
        return self._locks.setdefault(oid, asyncio.Lock())

    async def retrieve(self, object_id: str, query: str, top_k: int = 5,
                       working_messages: list | None = None) -> RecallResult:
        """检索四层记忆（首个 token 前完成）；召回即访问更新统计（持 per-oid 锁）"""
        working = working_messages or []
        if self.redis is None:
            return RecallResult(working=working)
        try:
            core = await store.get_core(self.redis, object_id)
            episodic = await store.get_episodic(self.redis, object_id, limit=3)
            long_all = await store.get_all_long_term(self.redis, object_id)
            long_hits, hit_mids = self.retriever.retrieve(long_all, query, top_k)
            if hit_mids:
                async with self._lock(object_id):
                    await store.touch_long_term(self.redis, object_id, hit_mids)
            return RecallResult(core=core, working=working, episodic=episodic,
                                long_term=long_hits, hit_mids=hit_mids)
        except Exception as e:
            logger.warning("memory retrieve 失败，返回空结果（降级不阻塞）: %s", e)
            return RecallResult(working=working)

    def render(self, result: RecallResult) -> str:
        """组装 memory_block：长期记忆 + 情景摘要（Core 已并入 persona system_prompt）"""
        blocks = []
        if result.long_term:
            facts = "\n".join(f"- {m.content}" for m in result.long_term)
            blocks.append(f"【相关长期记忆】\n{facts}")
        if result.episodic:
            sums = "\n".join(f"- {e.summary}" for e in result.episodic)
            blocks.append(f"【近期对话摘要】\n{sums}")
        return "\n\n".join(blocks)

    def _summary_model(self) -> str:
        from core.config import settings
        return settings.memory_summary_model or ""

    async def on_turn_complete(self, ctx) -> None:
        """对话后编码：Episodic 摘要（阈值触发）+ 反思 + Long-term 事实抽取（去重合并 + 上限淘汰）。
        内部 try/except 吞异常，绝不阻塞主回复"""
        from core.config import settings
        try:
            if self.redis is None:
                return
            oid = ctx.object_id
            model = self._summary_model()
            threshold = settings.memory_episodic_summarize_threshold
            turn_count = await store.get_turn_count(self.redis, oid)
            if (settings.memory_episodic_enable and threshold > 0 and turn_count > 0
                    and turn_count % threshold == 0):
                recent = await store.get_working_span(self.redis, oid, threshold)
                summary = await encoder.summarize(recent, self.llm, model)
                if summary:
                    await store.append_episodic(self.redis, oid, EpisodicEntry(
                        id=f"epi_{turn_count}",
                        summary=summary,
                        span_start_ts=ctx.created_ts or 0,
                        span_end_ts=ctx.created_ts or 0,
                        turn_range=(max(0, turn_count - threshold), turn_count),
                    ))
                epi_count = await store.count_episodic(self.redis, oid)
                if (epi_count > 0
                        and epi_count % settings.memory_episodic_reflect_interval == 0):
                    epis = await store.get_episodic(self.redis, oid, limit=10)
                    reflection = await encoder.reflect([e.summary for e in epis], self.llm, model)
                    if reflection:
                        await store.append_reflection(self.redis, oid, reflection)
            if settings.memory_longterm_enable and ctx.user_text:
                facts = await encoder.extract_facts(ctx.user_text, ctx.reply_text, self.llm, model)
                existing = await store.get_all_long_term(self.redis, oid)  # 本轮只拉一次
                async with self._lock(oid):
                    for f in facts:
                        await self._upsert_fact_dedup(oid, f, existing)
        except Exception as e:
            logger.exception("memory on_turn_complete failed: %s", e)

    async def _upsert_fact_dedup(self, oid: str, fact: dict,
                                 existing: list | None = None) -> None:
        """事实去重合并（精确归一化 + Jaccard）；existing 复用避免重复 HGETALL；
        新增后调 _enforce_max_facts 上限淘汰。调用方须持 _lock(oid)"""
        if existing is None:
            existing = await store.get_all_long_term(self.redis, oid)
        for m in existing:
            if _similar(m.content, fact["content"]):
                m.access_count += 1
                m.importance = max(m.importance, fact["importance"])
                if fact.get("emotion"):
                    m.emotion = max(m.emotion, fact["emotion"])
                await store.upsert_long_term(self.redis, oid, m)
                return
        new = MemoryItem(
            id=f"mem_{uuid.uuid4().hex[:12]}",
            content=fact["content"],
            category=Category(fact.get("category", "fact")),
            importance=fact["importance"],
            emotion=fact["emotion"],
            source="dialog",
        )
        await store.upsert_long_term(self.redis, oid, new)
        existing.append(new)
        await self._enforce_max_facts(oid, existing)

    async def _enforce_max_facts(self, oid: str, items: list) -> None:
        """长期记忆超上限淘汰：按 importance 升序软遗忘最低分条目（locked 豁免）"""
        from core.config import settings
        limit = settings.memory_longterm_max_facts
        if limit <= 0 or len(items) <= limit:
            return
        candidates = [m for m in items if not getattr(m, "locked", False)]
        candidates.sort(key=lambda m: getattr(m, "importance", 0.5))
        evict = [m.id for m in candidates[: len(items) - limit]]
        if evict:
            await store.mark_forgotten(self.redis, oid, evict)
            logger.info("long_term 超限淘汰 oid=%s count=%d", oid, len(evict))

    async def forget_tick(self) -> int:
        """遗忘批处理（独立定时任务）：软遗忘 + 上限淘汰 + forgotten 保留期物理清理。
        返回本次标记遗忘的条数"""
        from core.config import settings
        if self.redis is None:
            return 0
        cfg = ForgetConfig(
            w_importance=settings.memory_forget_w_importance,
            w_recency=settings.memory_forget_w_recency,
            w_access=settings.memory_forget_w_access,
            w_emotion=settings.memory_forget_w_emotion,
            retain_threshold=settings.memory_forget_threshold,
            decay_half_life_hours=settings.memory_forget_halflife_hours,
        )
        now = int(time.time() * 1000)
        marked = 0
        for oid in await store.list_objects(self.redis):
            async with self._lock(oid):
                items = await store.get_all_long_term(self.redis, oid, include_forgotten=False)
                # 1) 软遗忘（跌破 retain 阈值）
                to_forget = [m.id for m in items if should_forget(m, cfg, now)]
                if to_forget:
                    await store.mark_forgotten(self.redis, oid, to_forget)
                    marked += len(to_forget)
                # 2) 上限淘汰（按 retain_score 升序，locked 豁免）
                max_facts = settings.memory_longterm_max_facts
                if max_facts > 0 and len(items) > max_facts:
                    ranked = sorted(items, key=lambda m: retain_score(m, cfg, now))
                    evict = [m.id for m in ranked[: len(items) - max_facts]
                             if not getattr(m, "locked", False)]
                    if evict:
                        await store.mark_forgotten(self.redis, oid, evict)
                        marked += len(evict)
                # 3) forgotten 保留期物理清理（超 decay 半衰期 10 倍）
                retain_ms = int(cfg.decay_half_life_hours * 3600 * 1000 * 10)
                allm = await store.get_all_long_term(self.redis, oid, include_forgotten=True)
                purge = [m.id for m in allm
                         if m.forgotten and not getattr(m, "locked", False)
                         and m.created_ts and (now - m.created_ts) > retain_ms]
                if purge:
                    await store.delete_long_term(self.redis, oid, purge)
        return marked

    async def manual_forget(self, oid: str, mid: str) -> bool:
        """手动遗忘单条，返回是否存在"""
        if self.redis is None or not await store.get_long_term(self.redis, oid, mid):
            return False
        async with self._lock(oid):
            await store.mark_forgotten(self.redis, oid, [mid])
        return True

    async def restore(self, oid: str, mid: str) -> bool:
        """恢复已遗忘单条，返回是否存在"""
        if self.redis is None or not await store.get_long_term(self.redis, oid, mid):
            return False
        async with self._lock(oid):
            await store.restore_long_term(self.redis, oid, [mid])
        return True

    async def batch_forget(self, oid: str, category: str = "", keyword: str = "") -> int:
        """按 category/keyword 批量遗忘，返回遗忘条数"""
        if self.redis is None:
            return 0
        async with self._lock(oid):
            items = await store.get_all_long_term(self.redis, oid, include_forgotten=True)
            mids = []
            for m in items:
                if category and m.category.value != category:
                    continue
                if keyword and keyword not in m.content:
                    continue
                mids.append(m.id)
            if mids:
                await store.mark_forgotten(self.redis, oid, mids)
            return len(mids)

    async def record_negative_feedback(self, object_id: str, payload: dict) -> None:
        """记录负样本到 pending 队列（persona_evolve 反推回路，M4 消费）。失败不阻塞"""
        if self.redis is None:
            return
        try:
            from persona.store import get_object_persona_id
            pid = await get_object_persona_id(self.redis, object_id)
            await store.append_pending(self.redis, pid, {
                "type": "fact",
                "payload": payload,
                "source": object_id,
                "ts": int(time.time() * 1000),
                "status": "pending",
            })
        except Exception as e:
            logger.exception("record_negative_feedback failed: %s", e)


# ===== 常驻单例（双检锁 + 初始化降级）=====
_coordinator: MemoryCoordinator | None = None
_coord_lock = asyncio.Lock()


async def get_memory_coordinator() -> MemoryCoordinator:
    """获取记忆协调器单例（双检锁防并发重复初始化；初始化失败降级为空记忆单例）"""
    global _coordinator
    if _coordinator is None:
        async with _coord_lock:
            if _coordinator is None:
                try:
                    from storage.redis_client import get_redis
                    from llm.registry import get_provider, available_providers
                    from core.config import settings
                    redis = await get_redis()
                    llm = None
                    try:
                        pname = settings.memory_summary_provider or (
                            available_providers()[0] if available_providers() else "")
                        if pname:
                            llm = get_provider(pname)
                    except Exception as e:
                        logger.warning("memory LLM provider 初始化失败，编码将降级: %s", e)
                        llm = None
                    _coordinator = MemoryCoordinator(redis, llm_provider=llm)
                except Exception as e:
                    logger.warning("memory coordinator 初始化失败（redis 不可用？），降级空记忆: %s", e)
                    _coordinator = MemoryCoordinator(None, llm_provider=None)
    return _coordinator


def reset_coordinator() -> None:
    """重置单例（测试用）"""
    global _coordinator
    _coordinator = None
