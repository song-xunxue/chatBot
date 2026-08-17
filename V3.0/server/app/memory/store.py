"""
四级记忆存储(Redis 原语)
按层(Core/Episodic/Reflect/Long-term/State)封装 Redis 读写,纯存储不含算法。

V2.0 适配(M2):Working 层委托 V2.0 chat_store(block 三层)。
  - get_turn_count: 调 chat_store.count_messages(跨 block 统计) // 2
  - get_working_span: 调 chat_store.get_history(max_messages=turns*2)
  (V1.0 用扁平 List llen/lrange,V2.0 改 block 三层后这两处适配)

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植四级记忆存储到 V2.0;get_turn_count/get_working_span 适配 block 三层 chat_store

2026-07-07
变更说明：
  1. 记忆优化阶段1:新增记忆向量读写(set_vec/get_vec/get_vecs_bulk,独立 key 不污染 long Hash)
     + delete_long_term 一并清向量防脏
"""
import json
import time
from typing import Iterable

from redis.asyncio import Redis

from memory.models import MemoryItem, EpisodicEntry, CoreFact
from storage import chat_store

# 键模板(统一 mychat: 前缀)
_K_CORE = "mychat:mem:{oid}:core"
_K_EPISODIC = "mychat:mem:{oid}:episodic"
_K_REFLECT = "mychat:mem:{oid}:reflect"
_K_LONG = "mychat:mem:{oid}:long"
_K_VEC = "mychat:mem:{oid}:vec:{mid}"   # 记忆向量(独立存,不污染 long Hash;2026-07-07 向量检索)
_K_STATE = "mychat:state:{oid}"


# ===== Core 核心记忆(常驻,String JSON)=====
async def get_core(redis: Redis, oid: str) -> list[CoreFact]:
    raw = await redis.get(_K_CORE.format(oid=oid))
    if not raw:
        return []
    return [CoreFact.from_dict(d) for d in json.loads(raw)]


async def set_core(redis: Redis, oid: str, facts: list[CoreFact]) -> None:
    payload = json.dumps([f.to_dict() for f in facts], ensure_ascii=False)
    await redis.set(_K_CORE.format(oid=oid), payload)


# ===== Episodic 情景记忆摘要(ZSet, score=ts)=====
async def append_episodic(redis: Redis, oid: str, entry: EpisodicEntry) -> None:
    member = json.dumps(entry.to_dict(), ensure_ascii=False)
    await redis.zadd(_K_EPISODIC.format(oid=oid), {member: entry.created_ts})


async def get_episodic(redis: Redis, oid: str, limit: int = 3) -> list[EpisodicEntry]:
    # ZREVRANGE 按 score 倒序取最近 limit 条
    raw = await redis.zrevrange(_K_EPISODIC.format(oid=oid), 0, limit - 1)
    return [EpisodicEntry.from_dict(json.loads(m)) for m in raw]


async def count_episodic(redis: Redis, oid: str) -> int:
    return await redis.zcard(_K_EPISODIC.format(oid=oid))


async def prune_oldest_episodic(redis: Redis, oid: str, keep: int) -> int:
    """保留最近 keep 条 episodic(score=ts,ZSet 倒序最近),删更旧的。返回删除数(M4 睡眠巩固用)。"""
    key = _K_EPISODIC.format(oid=oid)
    total = await redis.zcard(key)
    if keep <= 0 or total <= keep:
        return 0
    rem = total - keep
    # ZSet 按 score 升序,rank 0..rem-1 为最旧;zremrangebyrank 删之
    await redis.zremrangebyrank(key, 0, rem - 1)
    return rem


# ===== Reflect 反思(List)=====
async def append_reflection(redis: Redis, oid: str, reflection: str,
                            span: tuple = (0, 0)) -> None:
    item = json.dumps({"reflection": reflection, "ts": int(time.time() * 1000),
                       "span": list(span)}, ensure_ascii=False)
    await redis.rpush(_K_REFLECT.format(oid=oid), item)


async def get_reflections(redis: Redis, oid: str, limit: int = 3) -> list[dict]:
    raw = await redis.lrange(_K_REFLECT.format(oid=oid), -limit, -1)
    return [json.loads(m) for m in raw]


# ===== Long-term 长期记忆(Hash, field=mid)=====
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
    """召回即访问:更新 last_access_ts + access_count(间隔重复效应)"""
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
    """物理删除长期记忆条目(HDEL)+ 关联向量(2026-07-07:向量独立 key,一并清防脏)"""
    pipe = redis.pipeline()
    pipe.hdel(_K_LONG.format(oid=oid), *list(mids))
    for mid in list(mids):
        pipe.delete(_K_VEC.format(oid=oid, mid=mid))
    await pipe.execute()


async def set_locked(redis: Redis, oid: str, mid: str, locked: bool) -> bool:
    """锁定/解锁长期记忆条目(防遗忘),返回是否找到该条目"""
    m = await get_long_term(redis, oid, mid)
    if not m:
        return False
    m.locked = locked
    await upsert_long_term(redis, oid, m)
    return True


async def update_long_term(redis: Redis, oid: str, mid: str, *,
                           content: str | None = None,
                           category=None, importance: float | None = None,
                           reason: str | None = None,
                           tags: list | None = None,
                           useful_score: float | None = None,
                           tier: int | None = None) -> bool:
    """编辑长期记忆条目(content/category/importance/reason/tags/useful_score/tier 任一)。
    返回是否找到。其他字段(access_count/locked/forgotten/...)保留不变。
    2026-08-13 加 reason/tags/useful_score/tier(三要素+用进废退手填)。"""
    m = await get_long_term(redis, oid, mid)
    if not m:
        return False
    if content is not None:
        m.content = content
    if category is not None:
        m.category = category
    if importance is not None:
        m.importance = max(0.0, min(1.0, float(importance)))
    if reason is not None:
        m.reason = str(reason)
    if tags is not None:
        # 容错 + 上限 5
        t = tags if isinstance(tags, list) else []
        m.tags = [str(x).strip() for x in t if str(x).strip()][:5]
    if useful_score is not None:
        m.useful_score = max(0.0, min(1.0, float(useful_score)))
    if tier is not None:
        m.tier = int(tier)
    await upsert_long_term(redis, oid, m)
    return True


# ===== 记忆向量(2026-07-07 向量检索,独立 key 不污染 long Hash)=====
async def set_vec(redis: Redis, oid: str, mid: str, vec: list[float]) -> None:
    """存记忆向量(JSON list[float]);写入时由 coordinator 调 embedding provider 生成"""
    await redis.set(_K_VEC.format(oid=oid, mid=mid), json.dumps(vec))


async def get_vec(redis: Redis, oid: str, mid: str) -> list[float] | None:
    """取单条记忆向量;无返回 None"""
    raw = await redis.get(_K_VEC.format(oid=oid, mid=mid))
    return json.loads(raw) if raw else None


async def get_vecs_bulk(redis: Redis, oid: str, mids: list[str]) -> dict[str, list[float]]:
    """批量取向量(管道 MGET);返回 {mid: vec},无向量的 mid 不在结果里(供检索 cosine rank)"""
    if not mids:
        return {}
    pipe = redis.pipeline()
    for mid in mids:
        pipe.get(_K_VEC.format(oid=oid, mid=mid))
    raws = await pipe.execute()
    return {mid: json.loads(r) for mid, r in zip(mids, raws) if r}


# ===== State 动态状态(Hash)=====
async def get_state(redis: Redis, oid: str) -> dict:
    return await redis.hgetall(_K_STATE.format(oid=oid))


async def set_state(redis: Redis, oid: str, partial: dict) -> None:
    if partial:
        partial = {**partial, "updated_ts": int(time.time() * 1000)}
        await redis.hset(_K_STATE.format(oid=oid), mapping=partial)


# ===== Working(委托 V2.0 chat_store block 三层,避免键耦合)=====
async def get_turn_count(redis: Redis, oid: str) -> int:
    """对话轮数 = 消息总数 // 2(一轮 = user + assistant);跨 block 统计。
    不等长对话下为近似轮数,episodic 阈值触发够用。"""
    n = await chat_store.count_messages(redis, oid)
    return n // 2


async def get_working_span(redis: Redis, oid: str, turns: int) -> list:
    """取最近 turns 轮原文(Message 列表)"""
    return await chat_store.get_history(redis, oid, max_messages=turns * 2)


# ===== 对象索引(forget_tick 遍历用)=====
async def list_objects(redis: Redis) -> list[str]:
    """扫描所有有长期记忆的对象 id(前/后缀切片,兼容含 ':' 的复合 oid)"""
    objs = set()
    prefix, suffix = "mychat:mem:", ":long"
    async for key in redis.scan_iter(match="mychat:mem:*:long", count=200):
        if key.startswith(prefix) and key.endswith(suffix):
            oid = key[len(prefix):-len(suffix)]
            if oid:
                objs.add(oid)
    return sorted(objs)


# ===== 反推 pending(persona_evolve 负样本,M3/M4 消费)=====
_K_PENDING = "mychat:persona:{pid}:pending"


async def append_pending(redis: Redis, persona_id: str, entry: dict) -> None:
    """追加一条 persona_evolve 待确认记录"""
    await redis.rpush(_K_PENDING.format(pid=persona_id),
                      json.dumps(entry, ensure_ascii=False))


async def list_pending(redis: Redis, persona_id: str) -> list[dict]:
    """列出 persona 的 pending 记录"""
    raw = await redis.lrange(_K_PENDING.format(pid=persona_id), 0, -1)
    return [json.loads(x) for x in raw]
