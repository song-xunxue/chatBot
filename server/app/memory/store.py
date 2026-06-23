"""
四级记忆存储（Redis 原语）
按层（Core/Episodic/Reflect/Long-term/State）封装 Redis 读写，纯存储不含算法。
对应 docs/04 §3.3、docs/09 §2.2/§4。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.2 创建四级记忆存储原语
"""
import json
import time
from typing import Iterable

from redis.asyncio import Redis

from memory.models import MemoryItem, EpisodicEntry, CoreFact
from storage import chat_store

# 键模板（统一 mychat: 前缀）
_K_CORE = "mychat:mem:{oid}:core"
_K_EPISODIC = "mychat:mem:{oid}:episodic"
_K_REFLECT = "mychat:mem:{oid}:reflect"
_K_LONG = "mychat:mem:{oid}:long"
_K_STATE = "mychat:state:{oid}"


# ===== Core 核心记忆（常驻，String JSON）=====
async def get_core(redis: Redis, oid: str) -> list[CoreFact]:
    raw = await redis.get(_K_CORE.format(oid=oid))
    if not raw:
        return []
    return [CoreFact.from_dict(d) for d in json.loads(raw)]


async def set_core(redis: Redis, oid: str, facts: list[CoreFact]) -> None:
    payload = json.dumps([f.to_dict() for f in facts], ensure_ascii=False)
    await redis.set(_K_CORE.format(oid=oid), payload)


# ===== Episodic 情景记忆摘要（ZSet, score=ts）=====
async def append_episodic(redis: Redis, oid: str, entry: EpisodicEntry) -> None:
    member = json.dumps(entry.to_dict(), ensure_ascii=False)
    await redis.zadd(_K_EPISODIC.format(oid=oid), {member: entry.created_ts})


async def get_episodic(redis: Redis, oid: str, limit: int = 3) -> list[EpisodicEntry]:
    # ZREVRANGE 按 score 倒序取最近 limit 条
    raw = await redis.zrevrange(_K_EPISODIC.format(oid=oid), 0, limit - 1)
    return [EpisodicEntry.from_dict(json.loads(m)) for m in raw]


async def count_episodic(redis: Redis, oid: str) -> int:
    return await redis.zcard(_K_EPISODIC.format(oid=oid))


# ===== Reflect 反思（List）=====
async def append_reflection(redis: Redis, oid: str, reflection: str,
                            span: tuple = (0, 0)) -> None:
    item = json.dumps({"reflection": reflection, "ts": int(time.time() * 1000),
                       "span": list(span)}, ensure_ascii=False)
    await redis.rpush(_K_REFLECT.format(oid=oid), item)


async def get_reflections(redis: Redis, oid: str, limit: int = 3) -> list[dict]:
    raw = await redis.lrange(_K_REFLECT.format(oid=oid), -limit, -1)
    return [json.loads(m) for m in raw]


# ===== Long-term 长期记忆（Hash, field=mid）=====
async def upsert_long_term(redis: Redis, oid: str, item: MemoryItem) -> None:
    await redis.hset(_K_LONG.format(oid=oid), item.id,
                     json.dumps(item.to_dict(), ensure_ascii=False))


async def get_long_term(redis: Redis, oid: str, mid: str) -> MemoryItem | None:
    raw = await redis.hget(_K_LONG.format(oid=oid), mid)
    return MemoryItem.from_dict(json.loads(raw)) if raw else None


async def get_all_long_term(redis: Redis, oid: str,
                            include_forgotten: bool = False) -> list[MemoryItem]:
    items = []
    for mid, raw in (await redis.hgetall(_K_LONG.format(oid=oid))).items():
        m = MemoryItem.from_dict(json.loads(raw))
        if include_forgotten or not m.forgotten:
            items.append(m)
    return items


async def touch_long_term(redis: Redis, oid: str, mids: Iterable[str]) -> None:
    """召回即访问：更新 last_access_ts + access_count（间隔重复效应）"""
    now = int(time.time() * 1000)
    for mid in mids:
        m = await get_long_term(redis, oid, mid)
        if m:
            m.last_access_ts = now
            m.access_count += 1
            await upsert_long_term(redis, oid, m)


async def mark_forgotten(redis: Redis, oid: str, mids: Iterable[str],
                         forgotten: bool = True) -> None:
    for mid in mids:
        m = await get_long_term(redis, oid, mid)
        if m:
            m.forgotten = forgotten
            await upsert_long_term(redis, oid, m)


async def restore_long_term(redis: Redis, oid: str, mids: Iterable[str]) -> None:
    await mark_forgotten(redis, oid, mids, forgotten=False)


async def delete_long_term(redis: Redis, oid: str, mids: Iterable[str]) -> None:
    """物理删除长期记忆条目（HDEL）"""
    await redis.hdel(_K_LONG.format(oid=oid), *list(mids))


async def set_locked(redis: Redis, oid: str, mid: str, locked: bool) -> bool:
    """锁定/解锁长期记忆条目（防遗忘），返回是否找到该条目"""
    m = await get_long_term(redis, oid, mid)
    if not m:
        return False
    m.locked = locked
    await upsert_long_term(redis, oid, m)
    return True


# ===== State 动态状态（Hash）=====
async def get_state(redis: Redis, oid: str) -> dict:
    return await redis.hgetall(_K_STATE.format(oid=oid))


async def set_state(redis: Redis, oid: str, partial: dict) -> None:
    if partial:
        partial = {**partial, "updated_ts": int(time.time() * 1000)}
        await redis.hset(_K_STATE.format(oid=oid), mapping=partial)


# ===== Working（委托 chat_store，避免键耦合）=====
async def get_turn_count(redis: Redis, oid: str) -> int:
    """对话轮数 = 工作记忆条数 // 2（一轮 = user + assistant）"""
    n = await redis.llen(chat_store._key(oid))
    return n // 2


async def get_working_span(redis: Redis, oid: str, turns: int) -> list:
    """取最近 turns 轮原文（Message 列表）"""
    return await chat_store.get_history(redis, oid, limit=turns * 2)


# ===== 对象索引（forget_tick 遍历用）=====
async def list_objects(redis: Redis) -> list[str]:
    """扫描所有有长期记忆的对象 id（前/后缀切片，兼容含 ':' 的复合 oid）"""
    objs = set()
    prefix, suffix = "mychat:mem:", ":long"
    async for key in redis.scan_iter(match="mychat:mem:*:long", count=200):
        if key.startswith(prefix) and key.endswith(suffix):
            oid = key[len(prefix):-len(suffix)]
            if oid:
                objs.add(oid)
    return sorted(objs)


# ===== 反推 pending（persona_evolve 负样本，M4 消费）=====
_K_PENDING = "mychat:persona:{pid}:pending"


async def append_pending(redis: Redis, persona_id: str, entry: dict) -> None:
    """追加一条 persona_evolve 待确认记录"""
    await redis.rpush(_K_PENDING.format(pid=persona_id),
                      json.dumps(entry, ensure_ascii=False))


async def list_pending(redis: Redis, persona_id: str) -> list[dict]:
    """列出 persona 的 pending 记录"""
    raw = await redis.lrange(_K_PENDING.format(pid=persona_id), 0, -1)
    return [json.loads(x) for x in raw]
