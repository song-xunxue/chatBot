"""
世界书存储(Redis 原语)+ 自动条目同步 + 命中记账(docs/09 §2.6/§3/§5)
键设计(全局,无 oid——V3.0 单人接管号,世界书跨会话共享):
  mychat:wb:entry:{id}            hash(字段=WbEntry.to_dict 扁平键)
  mychat:wb:ids                   zset(score=created_ts, member=id)
  mychat:wb:by_key:{归一key}      set(member=id;keys 反向索引,改 keys 时清理旧索引)
  mychat:wb:by_ref:{source}:{ref} string=条目id(幂等 upsert 索引,记忆同步/迁移用)
  mychat:wb:stats                 hash(全局注入统计:今日注入次数/平均 token 等)
纯存储不含注入算法(算法在 worldbook.py);所有对外写操作软失败不阻塞主链路由调用方保证。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:条目 CRUD + by_ref 幂等 upsert + record_injection 记账(hits/last_hit_at/
     last_injected_at + 全局 stats 跨日滚动) + sync_from_memory/sync_forget/
     sync_episodic 自动同步 + rebuild_auto 全量重建(迁移脚本/REST rebuild 共用)
"""
import logging
import time

from redis.asyncio import Redis

from memory import worldbook
from memory.worldbook import WbEntry

logger = logging.getLogger(__name__)

# 键模板(统一 mychat: 前缀)
_K_ENTRY = "mychat:wb:entry:{eid}"
_K_IDS = "mychat:wb:ids"
_K_BY_KEY = "mychat:wb:by_key:{key}"
_K_BY_REF = "mychat:wb:by_ref:{source}:{ref}"
_K_STATS = "mychat:wb:stats"

# 自动条目来源的默认参数(docs/09 §3:日记/梦低 order 低概率;summary 中间;memory 常规)
_AUTO_DEFAULTS = {
    "memory":   {"order": 100, "probability": 1.0, "position": "before_memories"},
    "summary":  {"order": 150, "probability": 0.7, "position": "before_memories"},
    "diary":    {"order": 200, "probability": 0.5, "position": "after_memories"},
    "dream":    {"order": 200, "probability": 0.5, "position": "after_memories"},
    "roleplay": {"order": 120, "probability": 0.8, "position": "before_memories"},
}


def _now_ms() -> int:
    return int(time.time() * 1000)


# ================ 条目 CRUD ================

async def upsert_entry(redis: Redis, entry: WbEntry) -> WbEntry:
    """写入条目(hash 全量覆盖 + zadd ids + 重建该条 by_key/by_ref 索引)。
    by_key 重建需先读旧条目拿旧 keys,避免改 keys 后旧索引残留"""
    old = await get_entry(redis, entry.id)
    entry.updated_ts = _now_ms()
    if not entry.token_estimate:
        entry.token_estimate = worldbook.estimate_tokens(entry.content)
    pipe = redis.pipeline()
    pipe.hset(_K_ENTRY.format(eid=entry.id), mapping=entry.to_redis())
    pipe.zadd(_K_IDS, {entry.id: entry.created_ts or _now_ms()})
    if old:
        for k in set(old.keys) | set(old.secondary_keys):
            pipe.srem(_K_BY_KEY.format(key=worldbook.normalize_for_match(k)), entry.id)
    for k in set(entry.keys) | set(entry.secondary_keys):
        nk = worldbook.normalize_for_match(k)
        if nk:
            pipe.sadd(_K_BY_KEY.format(key=nk), entry.id)
    # by_ref:已有旧 ref(改过 source_ref)清旧建新
    if old and old.source and old.source_ref:
        pipe.delete(_K_BY_REF.format(source=old.source, ref=old.source_ref))
    if entry.source and entry.source_ref:
        pipe.set(_K_BY_REF.format(source=entry.source, ref=entry.source_ref), entry.id)
    await pipe.execute()
    return entry


async def get_entry(redis: Redis, eid: str) -> WbEntry | None:
    raw = await redis.hgetall(_K_ENTRY.format(eid=eid))
    return WbEntry.from_dict(raw) if raw else None


async def list_entries(redis: Redis, *, source: str = "", enabled: bool | None = None,
                       limit: int = 0) -> list[WbEntry]:
    """列条目(created 倒序,新条目在前);source/enabled 可选过滤;limit>0 截断。
    直接遍历 ids zset 逐条 hgetall(条目百级量,pipeline 批量读)"""
    eids = await redis.zrevrange(_K_IDS, 0, -1)
    if not eids:
        return []
    pipe = redis.pipeline()
    for eid in eids:
        pipe.hgetall(_K_ENTRY.format(eid=eid))
    out = []
    for raw in await pipe.execute():
        if not raw:
            continue
        e = WbEntry.from_dict(raw)
        if source and e.source != source:
            continue
        if enabled is not None and e.enabled != enabled:
            continue
        out.append(e)
        if limit > 0 and len(out) >= limit:
            break
    return out


async def update_entry(redis: Redis, eid: str, patch: dict) -> WbEntry | None:
    """部分更新(面板编辑):patch 里出现的字段才覆盖,其余保留;返回更新后条目(无则 None)"""
    e = await get_entry(redis, eid)
    if not e:
        return None
    for k in ("title", "content", "key_regex", "mode", "position", "source", "source_ref"):
        if k in patch and patch[k] is not None:
            setattr(e, k, str(patch[k]))
    for k in ("order", "cooldown_minutes"):
        if patch.get(k) is not None:
            setattr(e, k, int(patch[k]))
    for k in ("probability", "weight"):
        if patch.get(k) is not None:
            setattr(e, k, max(0.0, min(1.0, float(patch[k]))))
    for k in ("keys", "secondary_keys"):
        v = patch.get(k)
        if isinstance(v, list):
            setattr(e, k, [str(x).strip() for x in v if str(x).strip()])
    if patch.get("enabled") is not None:
        e.enabled = bool(patch["enabled"])
    if "content" in patch and patch.get("content"):
        e.token_estimate = worldbook.estimate_tokens(e.content)
    return await upsert_entry(redis, e)


async def delete_entry(redis: Redis, eid: str) -> bool:
    """物理删除单条(REST DELETE;自动条目遗忘走 enabled=false 不走这)。
    清 hash + ids + by_key + by_ref"""
    e = await get_entry(redis, eid)
    if not e:
        return False
    pipe = redis.pipeline()
    pipe.delete(_K_ENTRY.format(eid=eid))
    pipe.zrem(_K_IDS, eid)
    for k in set(e.keys) | set(e.secondary_keys):
        pipe.srem(_K_BY_KEY.format(key=worldbook.normalize_for_match(k)), eid)
    if e.source and e.source_ref:
        pipe.delete(_K_BY_REF.format(source=e.source, ref=e.source_ref))
    await pipe.execute()
    return True


async def find_by_ref(redis: Redis, source: str, source_ref: str) -> WbEntry | None:
    """按来源索引找条目(幂等 upsert:命中即已有,更新而非新建)"""
    if not source or not source_ref:
        return None
    eid = await redis.get(_K_BY_REF.format(source=source, ref=source_ref))
    return await get_entry(redis, eid) if eid else None


def _ref_owner(source_ref: str) -> str:
    """从条目 source_ref 解析所属 oid。三种形态:core:{oid}:{key} / epi:{oid}:{eid} /
    {oid}:{mid}(长期记忆)。解析不出(手写/脏值)返空串"""
    ref = str(source_ref or "")
    for prefix in ("core:", "epi:"):
        if ref.startswith(prefix):
            ref = ref[len(prefix):]
            break
    return ref.split(":", 1)[0] if ":" in ref else ""


async def delete_all_auto(redis: Redis, oids: list[str] | None = None) -> int:
    """删除自动来源(memory/summary/diary/dream/roleplay)条目(manual 保留)。
    oids=None 全删;传列表只删属于这些对象的条目(source_ref 前缀归属判定)——
    审查修复:原版无条件全删,指定单对象的 rebuild 会静默删光其他对象的自动条目
    且不重建(用户在面板调过的 order/position 等全部丢失)。空列表直接返 0
    (无对象可重建时不动作量)。返回删除数"""
    if oids is not None and not oids:
        return 0
    owners = set(oids) if oids is not None else None
    entries = await list_entries(redis)
    n = 0
    for e in entries:
        if e.source not in worldbook.AUTO_SOURCES:
            continue
        if owners is not None and _ref_owner(e.source_ref) not in owners:
            continue
        await delete_entry(redis, e.id)
        n += 1
    return n


# ================ 命中记账(docs/09 §2.6) ================

async def record_injection(redis: Redis, eids: list[str], tokens: int) -> None:
    """注入记账:真实注入的条目 hits+=1 + last_hit_at/last_injected_at=now(Redis 直写);
    全局 stats 累计(total/day,day 跨日滚动)。失败仅告警不抛(调用点在注入主链路)"""
    try:
        now = _now_ms()
        pipe = redis.pipeline()
        for eid in eids:
            pipe.hincrby(_K_ENTRY.format(eid=eid), "hits", 1)
            pipe.hset(_K_ENTRY.format(eid=eid),
                      mapping={"last_hit_at": now, "last_injected_at": now})
        day = time.strftime("%Y-%m-%d")
        cur_day = await redis.hget(_K_STATS, "stat_day")
        if cur_day != day:
            # 跨日滚动:day_* 清零重计
            pipe.hset(_K_STATS, mapping={"stat_day": day, "day_injections": 0, "day_tokens": 0})
        pipe.hincrby(_K_STATS, "total_injections", 1)
        pipe.hincrby(_K_STATS, "day_injections", 1)
        pipe.hincrby(_K_STATS, "total_tokens", int(tokens))
        pipe.hincrby(_K_STATS, "day_tokens", int(tokens))
        await pipe.execute()
    except Exception as e:
        logger.warning("worldbook 注入记账失败(不阻塞主链路): %s", e)


async def record_hit(redis: Redis, eids: list[str]) -> None:
    """命中未注入记账(docs/09 §2.6:hits 不增,只统计真实注入;last_hit_at 仍刷,
    供「久未命中优先」排序)。失败仅告警不抛"""
    if not eids:
        return
    try:
        now = _now_ms()
        pipe = redis.pipeline()
        for eid in eids:
            pipe.hset(_K_ENTRY.format(eid=eid), mapping={"last_hit_at": now})
        await pipe.execute()
    except Exception as e:
        logger.warning("worldbook 命中记账失败(不阻塞主链路): %s", e)


async def get_stats(redis: Redis) -> dict:
    """全局统计(docs/09 §5 面板顶部):条目总数/启用数/常驻数/今日注入次数/平均注入 token/按来源分布"""
    entries = await list_entries(redis)
    raw = await redis.hgetall(_K_STATS)
    total_inj = int(raw.get("total_injections", 0) or 0)
    total_tok = int(raw.get("total_tokens", 0) or 0)
    by_source: dict[str, int] = {}
    for e in entries:
        by_source[e.source] = by_source.get(e.source, 0) + 1
    return {
        "total": len(entries),
        "enabled": sum(1 for e in entries if e.enabled),
        "always": sum(1 for e in entries if e.mode == "always"),
        "today_injections": int(raw.get("day_injections", 0) or 0),
        "avg_tokens": round(total_tok / total_inj, 1) if total_inj else 0.0,
        "by_source": by_source,
    }


# ================ 自动条目同步(docs/09 §3) ================

def _memory_source(item) -> tuple[str, dict]:
    """MemoryItem.source → 世界书 source + 默认参数(diary 按 tags 细分 dream/diary)"""
    src = getattr(item, "source", "") or ""
    tags = set(getattr(item, "tags", []) or [])
    if src == "diary":
        wb_src = "dream" if "dream" in tags else "diary"
    elif src == "roleplay":
        wb_src = "roleplay"
    else:
        wb_src = "memory"
    return wb_src, _AUTO_DEFAULTS[wb_src]


async def sync_from_memory(redis: Redis, oid: str, item, *, force_new: bool = False) -> WbEntry | None:
    """长期记忆 → 世界书条目(幂等 by source_ref="{oid}:{mid}")。
    已有条目只刷 content/keys/weight/token_estimate/enabled(用户在面板调过的
    order/position/probability/cooldown/mode 保留);新建用来源默认参数。
    weight=useful_score(接三档衰减,docs §1);遗忘态 → enabled=False。软失败返 None"""
    try:
        wb_src, default = _memory_source(item)
        ref = f"{oid}:{item.id}"
        exist = await find_by_ref(redis, wb_src, ref)
        if exist and not force_new:
            exist.content = item.content
            keys = worldbook.auto_keys(item.content)
            for t in getattr(item, "tags", []) or []:
                if t and t not in keys:
                    keys.append(str(t))
            exist.keys = keys[:8]
            exist.weight = max(0.0, min(1.0, float(getattr(item, "useful_score", 0.5))))
            exist.token_estimate = worldbook.estimate_tokens(item.content)
            exist.enabled = not getattr(item, "forgotten", False)
            return await upsert_entry(redis, exist)
        keys = worldbook.auto_keys(item.content)
        for t in getattr(item, "tags", []) or []:
            if t and t not in keys:
                keys.append(str(t))
        return await upsert_entry(redis, WbEntry(
            id=worldbook.new_entry_id(),
            title=(item.content or "")[:16],
            content=item.content or "",
            keys=keys[:8],
            mode="trigger",
            order=default["order"],
            position=default["position"],
            probability=default["probability"],
            enabled=not getattr(item, "forgotten", False),
            source=wb_src,
            source_ref=ref,
            weight=max(0.0, min(1.0, float(getattr(item, "useful_score", 0.5)))),
        ))
    except Exception as e:
        logger.warning("worldbook sync_from_memory 失败(不阻塞记忆写入): %s", e)
        return None


async def sync_core_fact(redis: Redis, oid: str, fact) -> WbEntry | None:
    """核心记忆(常驻)→ mode=always 条目(source=memory,ref="core:{oid}:{key}")。
    core 层在 legacy 是常驻注入,映射到世界书保持常驻语义(docs §3 表格)"""
    try:
        ref = f"core:{oid}:{getattr(fact, 'key', '')}"
        content = getattr(fact, "content", "") or ""
        exist = await find_by_ref(redis, "memory", ref)
        if exist:
            exist.content = content
            exist.token_estimate = worldbook.estimate_tokens(content)
            exist.enabled = True
            return await upsert_entry(redis, exist)
        return await upsert_entry(redis, WbEntry(
            id=worldbook.new_entry_id(),
            title=content[:16],
            content=content,
            keys=[],
            mode="always",
            order=50,
            position="before_memories",
            source="memory",
            source_ref=ref,
            weight=1.0,
        ))
    except Exception as e:
        logger.warning("worldbook sync_core_fact 失败(不阻塞): %s", e)
        return None


async def sync_episodic(redis: Redis, oid: str, entry) -> WbEntry | None:
    """情景摘要 → source=summary 条目(幂等 by "epi:{oid}:{eid}")。
    keys 取摘要自动关键词(docs §3:keys 取摘要关键词)"""
    try:
        ref = f"epi:{oid}:{getattr(entry, 'id', '')}"
        summary = getattr(entry, "summary", "") or ""
        exist = await find_by_ref(redis, "summary", ref)
        if exist:
            exist.content = summary
            exist.keys = worldbook.auto_keys(summary)
            exist.token_estimate = worldbook.estimate_tokens(summary)
            return await upsert_entry(redis, exist)
        default = _AUTO_DEFAULTS["summary"]
        return await upsert_entry(redis, WbEntry(
            id=worldbook.new_entry_id(),
            title=summary[:16],
            content=summary,
            keys=worldbook.auto_keys(summary),
            mode="trigger",
            order=default["order"],
            position=default["position"],
            probability=default["probability"],
            source="summary",
            source_ref=ref,
            weight=0.5,
        ))
    except Exception as e:
        logger.warning("worldbook sync_episodic 失败(不阻塞): %s", e)
        return None


async def sync_forget(redis: Redis, oid: str, mids, forgotten: bool) -> None:
    """记忆遗忘/恢复 → 对应条目 enabled 同步(遗忘置 False 不物理删,docs §3)。
    软失败(mark_forgotten 全路径共用,绝不能炸记忆主链路)"""
    try:
        for mid in list(mids):
            # 条目来源不确定(memory/diary/dream/roleplay 都可能),扫 4 类 ref 前缀都试
            for src in ("memory", "diary", "dream", "roleplay"):
                e = await find_by_ref(redis, src, f"{oid}:{mid}")
                if e:
                    e.enabled = not forgotten
                    await upsert_entry(redis, e)
    except Exception as e:
        logger.warning("worldbook sync_forget 失败(不阻塞遗忘主链路): %s", e)


# ================ 全量重建(迁移脚本/REST rebuild 共用) ================

async def rebuild_auto(redis: Redis, oids: list[str], *, dry_run: bool = False) -> dict:
    """从现有记忆体系全量重建自动条目(幂等:先删全部 AUTO_SOURCES 条目再按当前数据重建,
    重复执行结果一致;manual 条目不受影响)。来源:long_term(遗忘→disabled)+
    core(→always)+episodic(→summary)。返回 {"created","disabled","oids"}(dry_run 只统计)"""
    from memory import store as mem_store
    created = disabled = 0
    if not dry_run:
        # 只清本轮要重建的对象的自动条目(审查修复:原版全局清场,单对象 rebuild
        # 会误删其他对象条目;oids 传给 delete_all_auto 按 source_ref 归属过滤)
        await delete_all_auto(redis, oids=oids)
    for oid in oids:
        items = await mem_store.get_all_long_term(redis, oid, include_forgotten=True)
        core = await mem_store.get_core(redis, oid)
        epis = await mem_store.get_episodic(redis, oid, limit=100)
        for m in items:
            if dry_run:
                if m.forgotten:
                    disabled += 1
                else:
                    created += 1
                continue
            e = await sync_from_memory(redis, oid, m)
            if e is None:
                continue
            if e.enabled:
                created += 1
            else:
                disabled += 1
        for f in core:
            if dry_run:
                created += 1
                continue
            if await sync_core_fact(redis, oid, f) is not None:
                created += 1
        for ep in epis:
            if dry_run:
                created += 1
                continue
            if await sync_episodic(redis, oid, ep) is not None:
                created += 1
    return {"created": created, "disabled": disabled, "oids": list(oids)}
