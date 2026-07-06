"""
记忆协调器 MemoryCoordinator
串联检索→组装→编码→遗忘,服务端常驻单例,对外唯一记忆入口。
retrieve/render(检索组装);on_turn_complete(编码);forget_tick/手动遗忘。
per-oid 锁(RMW 一致性)、上限淘汰+物理清理、单例双检锁+初始化降级、事实去重归一化。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 coordinator 到 V2.0(零业务改动;on_turn_complete 经 store 适配 block chat_store)

2026-07-07
变更说明：
  1. 记忆优化阶段1/2/3:retrieve 加向量重排(BM25+embedding RRF)+ _upsert_fact_dedup 语义去重
     (cosine 替 Jaccard)+ extract 批量化(每 N 轮)+ 评分联动 importance + 激活 core 层(渲染+升级)
"""
import asyncio
import logging
import re
import time
import uuid

from redis.asyncio import Redis

from memory import store, encoder
from memory.models import RecallResult, ForgetConfig, EpisodicEntry, MemoryItem, Category
from memory.retriever import KeywordRetriever, BM25Retriever, sample_weighted, _tokenize
from memory.forgetting import should_forget, retain_score

logger = logging.getLogger(__name__)

# 去重相似度阈值(关键词 Jaccard),超过则视为重复事实做合并
_DEDUP_THRESHOLD = 0.3


def _normalize(s: str) -> str:
    """归一化:去标点与空白,便于精确相等判定"""
    return re.sub(r"\s+|[^一-龥a-zA-Z0-9]", "", (s or "").lower())


def _similar(a: str, b: str, threshold: float = _DEDUP_THRESHOLD) -> bool:
    """事实去重:先精确归一化相等判定,否则关键词 Jaccard(首版,零依赖)"""
    if _normalize(a) == _normalize(b):
        return True
    ta, tb = set(_tokenize(a)), set(_tokenize(b))
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


class MemoryCoordinator:
    """记忆协调器:检索→组装→编码→遗忘的唯一入口,服务端常驻"""

    def __init__(self, redis: Redis | None, llm_provider=None, cfg: ForgetConfig | None = None):
        self.redis = redis
        self.llm = llm_provider  # 编码用 LLM,None 时降级
        self.cfg = cfg or ForgetConfig()
        self.retriever = self._make_retriever()
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _make_retriever():
        """按 config 选检索器(M4):bm25(默认 BM25 评分)/ keyword(交集计数)"""
        from core.config import settings
        return KeywordRetriever() if settings.memory_retriever == "keyword" else BM25Retriever()

    def _lock(self, oid: str) -> asyncio.Lock:
        """per-object 锁:串行化同一对象的读-改-写,避免 access_count/去重并发覆盖"""
        return self._locks.setdefault(oid, asyncio.Lock())

    async def retrieve(self, object_id: str, query: str, top_k: int = 5,
                       working_messages: list | None = None) -> RecallResult:
        """检索四层记忆(首个 token 前完成);召回即访问更新统计(持 per-oid 锁)"""
        working = working_messages or []
        if self.redis is None:
            return RecallResult(working=working)
        try:
            from core.config import settings
            core = await store.get_core(self.redis, object_id)
            episodic = await store.get_episodic(self.redis, object_id, limit=3)
            long_all = await store.get_all_long_term(self.redis, object_id)
            # M4:rank 打分后按 config 决定 加权随机召回(避确定性偏见)/ 确定性 top-K
            ranked = self.retriever.rank(long_all, query)
            ranked = await self._embedding_rerank(object_id, query, long_all, ranked)
            if settings.memory_weighted_sample and ranked:
                long_hits = sample_weighted(ranked, top_k)
            else:
                long_hits = [m for _, m in ranked[:top_k]]
            hit_mids = [m.id for m in long_hits]
            if hit_mids:
                async with self._lock(object_id):
                    await store.touch_long_term(self.redis, object_id, hit_mids)
            return RecallResult(core=core, working=working, episodic=episodic,
                                long_term=long_hits, hit_mids=hit_mids)
        except Exception as e:
            logger.warning("memory retrieve 失败,返回空结果(降级不阻塞): %s", e)
            return RecallResult(working=working)

    async def _embedding_rerank(self, oid: str, query: str, long_all: list,
                                ranked_bm25: list) -> list:
        """向量语义重排(2026-07-07 优化1):BM25 + embedding RRF 融合。
        provider 未配置/失败/无候选 → 返回原 BM25(降级,不影响现有)。
        懒 embed:候选无 vec 的现场 embed + 存(首次检索补全,后续命中)。"""
        from core.config import settings
        from llm.embedding import get_embedding_provider
        from memory.retriever import cosine_similarity, rrf_fuse
        if not long_all:
            return ranked_bm25
        provider = get_embedding_provider()
        if provider is None:
            return ranked_bm25   # 未配置 embedding,纯 BM25
        try:
            query_vec = (await provider.embed([query], settings.memory_embedding_model))[0]
            if not query_vec:
                return ranked_bm25
            mids = [m.id for m in long_all]
            vec_map = await store.get_vecs_bulk(self.redis, oid, mids)
            # 懒 embed:无 vec 的候选现场补(写存,后续命中)
            missing = [m for m in long_all if m.id not in vec_map]
            if missing:
                new_vecs = await provider.embed([m.content for m in missing],
                                                settings.memory_embedding_model)
                for m, v in zip(missing, new_vecs):
                    if v:
                        await store.set_vec(self.redis, oid, m.id, v)
                        vec_map[m.id] = v
            # cosine rank(仅对有 vec 的候选;sim>0 才计入)
            ranked_emb = []
            for m in long_all:
                v = vec_map.get(m.id)
                if v:
                    sim = cosine_similarity(query_vec, v)
                    if sim > 0:
                        ranked_emb.append((sim, m))
            if not ranked_emb:
                return ranked_bm25
            ranked_emb.sort(key=lambda x: x[0], reverse=True)
            return rrf_fuse(ranked_bm25, ranked_emb)
        except Exception as e:
            logger.warning("embedding 重排失败,降级 BM25: %s", e)
            return ranked_bm25

    async def _embed_fact(self, content: str) -> list[float] | None:
        """单条文本 embed(供语义去重用);provider 未配置/失败返 None(调用方降级 Jaccard)"""
        from core.config import settings
        from llm.embedding import get_embedding_provider
        provider = get_embedding_provider()
        if provider is None or not content:
            return None
        try:
            vecs = await provider.embed([content], settings.memory_embedding_model)
            return vecs[0] if vecs else None
        except Exception as e:
            logger.warning("embed_fact 失败,降级: %s", e)
            return None

    async def _upsert_core_fact(self, oid: str, fact: dict) -> None:
        """高重要度事实升级到 core 层(常驻注入,2026-07-07 优化4)。
        按 content 归一化 + Jaccard 去重(避免核心记忆重复堆积)。
        core 层在 retrieve 取全量 + render 常驻注入,不靠检索运气。"""
        core_list = await store.get_core(self.redis, oid)
        content = fact.get("content", "")
        for cf in core_list:
            if _normalize(cf.content) == _normalize(content) or _similar(cf.content, content):
                return   # 已存在(去重)
        from memory.models import CoreFact
        core_list.append(CoreFact(
            key=f"{fact.get('category', 'fact')}:{_normalize(content)[:32]}",
            content=content,
        ))
        await store.set_core(self.redis, oid, core_list)

    def render(self, result: RecallResult) -> str:
        """组装 memory_block:核心记忆(常驻) + 长期记忆(召回) + 情景摘要。
        2026-07-07 优化4:激活 core 层渲染(原 retrieve 取了 core 但 render 不用,是死代码)。"""
        blocks = []
        if result.core:
            core_facts = "\n".join(f"- {f.content}" for f in result.core)
            blocks.append(f"【核心记忆】\n{core_facts}")
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
        """对话后编码:Episodic 摘要(阈值触发)+ 反思 + Long-term 事实抽取(去重合并 + 上限淘汰)。
        内部 try/except 吞异常,绝不阻塞主回复"""
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
            # 2026-07-07 优化3:长期事实批量提取(每 N 轮一次,替每轮单条,降 LLM 成本)
            extract_n = settings.memory_longterm_extract_threshold
            if (settings.memory_longterm_enable and extract_n > 0
                    and turn_count > 0 and turn_count % extract_n == 0):
                recent = await store.get_working_span(self.redis, oid, extract_n)
                facts = await encoder.extract_facts_batch(recent, self.llm, model)
                if facts:
                    # 2026-07-07 优化3:评分联动 importance(本轮高分 +0.1 强化/低分 -0.1 弱化新 facts)
                    score_final = getattr(ctx, "last_score", -1.0)
                    if score_final >= 0:
                        delta = 0.1 if score_final >= 85 else (-0.1 if score_final < 60 else 0.0)
                        if delta:
                            for f in facts:
                                f["importance"] = max(0.0, min(1.0, float(f.get("importance", 0.5)) + delta))
                    existing = await store.get_all_long_term(self.redis, oid)  # 本批只拉一次
                    async with self._lock(oid):
                        for f in facts:
                            await self._upsert_fact_dedup(oid, f, existing)
                            # 2026-07-07 优化4:高重要度/关系事实升级 core 层(常驻注入)
                            if float(f.get("importance", 0)) >= 0.8 or f.get("category") == "relationship":
                                await self._upsert_core_fact(oid, f)
        except Exception as e:
            logger.exception("memory on_turn_complete failed: %s", e)

    async def upsert_fact(self, oid: str, fact: dict) -> bool:
        """公开:写入一条长期事实(去重合并 + 上限淘汰)。供外部单条写入(如 write_memory 工具)——
        不再让外部深入私有 _upsert_fact_dedup/_lock(架构 #6 收口)。
        内部持 _lock(oid) 串行化 + 拉 existing,委托 _upsert_fact_dedup(批量内部用,调用方持锁)。
        redis 不可用返 False。"""
        if self.redis is None:
            return False
        async with self._lock(oid):
            existing = await store.get_all_long_term(self.redis, oid)
            await self._upsert_fact_dedup(oid, fact, existing)
        return True

    async def _upsert_fact_dedup(self, oid: str, fact: dict,
                                 existing: list | None = None) -> None:
        """事实去重合并 + 写向量(2026-07-07 优化2:语义去重 cosine 优先,降级 Jaccard);
        existing 复用避免重复 HGETALL;新增后调 _enforce_max_facts 上限淘汰。
        内部原语:调用方须持 _lock(oid)(on_turn_complete 批量 / consolidate_sleep 巩固);
        外部单条写入走公开 upsert_fact(自管锁,架构 #6)。"""
        from core.config import settings
        from memory.retriever import cosine_similarity
        if existing is None:
            existing = await store.get_all_long_term(self.redis, oid)
        # 先 embed 新 fact(供语义去重 + 新建时存)
        new_vec = await self._embed_fact(fact["content"])
        dup_found = False
        if new_vec:
            # cosine 语义去重:对比已有记忆向量(懒 embed 补老数据缺失的 vec)
            existing_vecs = await store.get_vecs_bulk(self.redis, oid, [m.id for m in existing])
            for m in existing:
                v = existing_vecs.get(m.id)
                if v is None:
                    v = await self._embed_fact(m.content)   # 老数据懒补
                    if v:
                        await store.set_vec(self.redis, oid, m.id, v)
                if v and cosine_similarity(new_vec, v) >= settings.memory_embedding_sim_threshold:
                    m.access_count += 1
                    m.importance = max(m.importance, fact["importance"])
                    if fact.get("emotion"):
                        m.emotion = max(m.emotion, fact["emotion"])
                    await store.upsert_long_term(self.redis, oid, m)
                    dup_found = True
                    break
        else:
            # 降级 Jaccard(无 embedding provider)
            for m in existing:
                if _similar(m.content, fact["content"]):
                    m.access_count += 1
                    m.importance = max(m.importance, fact["importance"])
                    if fact.get("emotion"):
                        m.emotion = max(m.emotion, fact["emotion"])
                    await store.upsert_long_term(self.redis, oid, m)
                    dup_found = True
                    break
        if dup_found:
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
        if new_vec:
            await store.set_vec(self.redis, oid, new.id, new_vec)   # 新建记忆同步存 vec
        existing.append(new)
        await self._enforce_max_facts(oid, existing)

    async def _enforce_max_facts(self, oid: str, items: list) -> None:
        """长期记忆超上限淘汰:按 importance 升序软遗忘最低分条目(locked 豁免)"""
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
        """遗忘批处理(独立定时任务):软遗忘 + 上限淘汰 + forgotten 保留期物理清理。
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
                # 1) 软遗忘(跌破 retain 阈值)
                to_forget = [m.id for m in items if should_forget(m, cfg, now)]
                if to_forget:
                    await store.mark_forgotten(self.redis, oid, to_forget)
                    marked += len(to_forget)
                # 2) 上限淘汰(按 retain_score 升序,locked 豁免)
                max_facts = settings.memory_longterm_max_facts
                if max_facts > 0 and len(items) > max_facts:
                    ranked = sorted(items, key=lambda m: retain_score(m, cfg, now))
                    evict = [m.id for m in ranked[: len(items) - max_facts]
                             if not getattr(m, "locked", False)]
                    if evict:
                        await store.mark_forgotten(self.redis, oid, evict)
                        marked += len(evict)
                # 3) forgotten 保留期物理清理(超 decay 半衰期 10 倍)
                retain_ms = int(cfg.decay_half_life_hours * 3600 * 1000 * 10)
                allm = await store.get_all_long_term(self.redis, oid, include_forgotten=True)
                purge = [m.id for m in allm
                         if m.forgotten and not getattr(m, "locked", False)
                         and m.created_ts and (now - m.created_ts) > retain_ms]
                if purge:
                    await store.delete_long_term(self.redis, oid, purge)
                # 4) M4 睡眠巩固(episodic 摘要→long-term fact + 冗余 episodic 清理;调用方持锁)
                if settings.memory_consolidate_enable:
                    from memory.consolidation import consolidate_sleep
                    await consolidate_sleep(self.redis, oid, self.llm,
                                            self._summary_model(), coordinator=self)
        return marked

    async def manual_forget(self, oid: str, mid: str) -> bool:
        """手动遗忘单条,返回是否存在"""
        if self.redis is None or not await store.get_long_term(self.redis, oid, mid):
            return False
        async with self._lock(oid):
            await store.mark_forgotten(self.redis, oid, [mid])
        return True

    async def restore(self, oid: str, mid: str) -> bool:
        """恢复已遗忘单条,返回是否存在"""
        if self.redis is None or not await store.get_long_term(self.redis, oid, mid):
            return False
        async with self._lock(oid):
            await store.restore_long_term(self.redis, oid, [mid])
        return True

    async def batch_forget(self, oid: str, category: str = "", keyword: str = "") -> int:
        """按 category/keyword 批量遗忘,返回遗忘条数"""
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
        """记录负样本到 pending 队列(persona_evolve 反推回路,M3/M4 消费)。失败不阻塞"""
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


# ===== 常驻单例(双检锁 + 初始化降级)=====
_coordinator: MemoryCoordinator | None = None
_coord_lock = asyncio.Lock()


async def get_memory_coordinator() -> MemoryCoordinator:
    """获取记忆协调器单例(双检锁防并发重复初始化;初始化失败降级为空记忆单例)"""
    global _coordinator
    if _coordinator is None:
        async with _coord_lock:
            if _coordinator is None:
                try:
                    from storage.redis_client import get_redis
                    from llm.resolver import resolve_provider
                    redis = await get_redis()
                    llm = resolve_provider("memory")   # key 未配返 None→编码降级;统一解析链免散落 or 兜底
                    _coordinator = MemoryCoordinator(redis, llm_provider=llm)
                except Exception as e:
                    logger.warning("memory coordinator 初始化失败(redis 不可用?),降级空记忆: %s", e)
                    _coordinator = MemoryCoordinator(None, llm_provider=None)
    return _coordinator


def reset_coordinator() -> None:
    """重置单例(测试用)"""
    global _coordinator
    _coordinator = None
