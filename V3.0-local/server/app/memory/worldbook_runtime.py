"""
世界书注入运行时(组合 worldbook 纯逻辑 + worldbook_store 存储 + 记忆 retriever 兜底)
inject:stage_memory_retrieve 的 MEMORY_MODE=worldbook 分支调用——
  全量条目 → 候选收集(keys/regex 命中) → 过滤(冷却/概率) → 排序 → 预算裁剪 →
  memory 来源不足时向量召回兜底补(recall_topup,临时条目不落库) → 分 position 渲染 →
  ctx.worldbook_sections(锚点插 system prompt)+ 记账(注入 hits/命中 last_hit_at)。
MEMORY_MODE=legacy 时本模块完全不被调用(行为与既有逐字一致,验收#1)。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:inject 一站式注入 + _topup_from_retriever 向量兜底(复用 coordinator.retrieve,
     兜底召回走临时条目渲染,不写世界书;hit_mids 照旧回填 memory_meta 维持评分回流)
  2. 审查修复(RL 回流对齐 legacy):①经世界书注入的既有 memory 条目,其 mid 一并进
     hit_mids(评分驱动 useful_score ±0.1 回流)并补 touch_long_term(遗忘衰减 access
     权重依赖访问统计;兜底召回的在 retrieve 内已 touch,跳过防同轮双计);②topup 空缺
     判定只数 mode=trigger 的 memory 条目——core 常驻(sync_core_fact 也是 source=
     memory,mode=always)不该占用"候选不足"的补足配额,否则 core 数量达到 topup 上
     限时兜底恒不触发、hit_mids 恒空,反馈回路彻底静默
"""
import logging
import random
import time

from memory import worldbook, worldbook_store
from memory.worldbook import WbEntry

logger = logging.getLogger(__name__)

# 兜底召回条目的注入参数(order 极大保证排在正式条目之后;weight=useful_score 传入)
_TOPUP_ORDER = 9999


def _now_ms() -> int:
    return int(time.time() * 1000)


def _mid_from_ref(source_ref: str) -> str | None:
    """memory 来源条目 source_ref({oid}:{mid})解析出 mid(供 RL 回流/touch)。
    core:/epi: 前缀(常驻/摘要,无对应长期记忆 mid)与脏值返 None"""
    ref = str(source_ref or "")
    if not ref or ref.startswith(("core:", "epi:")):
        return None
    parts = ref.split(":", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None


def _recent_texts(ctx, turns: int = 2) -> list[str]:
    """匹配文本 = 当前用户消息 + 最近 turns 轮对话(docs/09 §2 输入)。
    从 ctx.history 尾部取 turns*2 条 Message 的 content"""
    texts = [ctx.user_text or ""]
    for m in (ctx.history or [])[-(turns * 2):]:
        c = getattr(m, "content", "")
        if c:
            texts.append(c)
    return texts


async def _topup_from_retriever(ctx, redis, n: int) -> tuple[list[WbEntry], list[str]]:
    """向量兜底(docs/09 §2.1c):候选中 memory 来源不足时,用现有 coordinator.retrieve
    (BM25+向量 RRF,自带 touch 访问统计)召回 top-n 长期记忆,转临时 WbEntry 参与渲染。
    临时条目不写世界书(它们已有记忆主链路管理)。返回 (临时条目, 召回 mid 列表)——
    mids 由调用方统一写 memory_meta.hit_mids,维持评分 RL 回流口径与 legacy 对齐"""
    out: list[WbEntry] = []
    hit: list[str] = []
    try:
        from memory.coordinator import get_memory_coordinator
        coord = await get_memory_coordinator()
        if coord.redis is None:
            return out, hit
        result = await coord.retrieve(ctx.object_id, ctx.user_text,
                                      top_k=n, working_messages=ctx.history)
        hit = [str(x) for x in (result.hit_mids or [])]
        for m in result.long_term or []:
            if not m or getattr(m, "forgotten", False):
                continue
            out.append(WbEntry(
                id=f"topup_{m.id}",
                title=(m.content or "")[:16],
                content=m.content or "",
                keys=[],
                mode="trigger",
                order=_TOPUP_ORDER,
                position="before_memories",
                probability=1.0,
                source="memory",
                source_ref=f"{ctx.object_id}:{m.id}",
                weight=max(0.0, min(1.0, float(getattr(m, "useful_score", 0.5)))),
            ))
    except Exception as e:
        logger.warning("worldbook 向量兜底召回失败(降级不补): %s", e)
    return out, hit


async def inject(ctx, redis) -> None:
    """世界书注入主入口:填 ctx.worldbook_sections(position→文本)与 ctx.memory_meta。
    worldbook 模式下不再生成 legacy memory_block(core/长期/episodic 全量摘要注入停用)。
    全程软失败:任何异常告警后置空 sections(退化为无人设记忆注入,不炸回复主链路)"""
    try:
        from core.config import settings
        entries = await worldbook_store.list_entries(redis)
        now = _now_ms()
        result = worldbook.select_for_injection(
            entries, _recent_texts(ctx), now,
            budget=settings.worldbook_budget,
            max_entries=settings.worldbook_max_entries,
            rng=random.Random(),
        )
        kept: list[WbEntry] = result["kept"]
        # 向量兜底:kept 中 trigger 型 memory 条目 < recall_topup 时补足(docs/09 §2.1c:
        # 「候选不足时兜底,不替代手动设定」)。只数 mode=trigger——core 常驻条目
        # (source 也是 memory)是"本就该在"的常驻注入,不算候选空缺(审查修复②)
        mem_count = sum(1 for e in kept if e.source == "memory" and e.mode == "trigger")
        topup_n = settings.worldbook_recall_topup - mem_count
        topup_entries: list[WbEntry] = []
        hit_mids: list[str] = []
        if topup_n > 0:
            topup_entries, hit_mids = await _topup_from_retriever(ctx, redis, topup_n)
            kept = kept + topup_entries
        # RL 回流对齐 legacy(审查修复①):经世界书命中的既有 memory 条目,mid 并入
        # hit_mids(评分 _apply_score_to_recalled 消费 useful_score ±0.1);并补 touch
        # 访问统计——遗忘衰减 retain_score 的 access 权重依赖它,不 touch 会长期失真。
        # topup_ 条目跳过:coordinator.retrieve 内部已 touch,防同轮双计
        touched_extra: list[str] = []
        for e in kept:
            if e.id.startswith("topup_"):
                continue
            mid = _mid_from_ref(getattr(e, "source_ref", ""))
            if mid:
                if mid not in hit_mids:
                    hit_mids.append(mid)
                if mid not in touched_extra:
                    touched_extra.append(mid)
        if touched_extra:
            try:
                from memory import store as mem_store
                await mem_store.touch_long_term(redis, ctx.object_id, touched_extra)
            except Exception as te:
                logger.warning("worldbook touch 命中记忆失败(软失败): %s", te)
        sections = worldbook.render_sections(kept)
        tokens = sum(e.token_estimate for e in kept)
        injected_ids = [e.id for e in kept if not e.id.startswith("topup_")]
        ctx.worldbook_sections = sections
        ctx.memory_meta = {
            "worldbook_injected": injected_ids,
            "worldbook_tokens": tokens,
            # RL 回流 mid 全集(兜底召回 + 世界书命中的既有 memory 条目;
            # _apply_score_to_recalled 消费;无任何命中为空列表)
            "hit_mids": hit_mids,
        }
        # 记账:注入的 hits+1/last_injected_at;命中但被冷却/概率/裁剪刷掉的只刷 last_hit_at
        hit_only = [eid for eid in result["hit_ids"] if eid not in set(injected_ids)]
        if injected_ids:
            await worldbook_store.record_injection(redis, injected_ids, tokens)
        await worldbook_store.record_hit(redis, hit_only)
        logger.debug("worldbook 注入 oid=%s entries=%d tokens=%d dropped=%d%s",
                     ctx.object_id, len(kept), tokens, len(result["dropped"]),
                     "(+topup)" if topup_n > 0 else "")
    except Exception as e:
        logger.warning("worldbook 注入失败(降级空注入,不阻塞回复): %s", e)
        ctx.worldbook_sections = {}
