"""
代人聊天 B 实时接管服务（V1.1 M13）
per-object 代人模式开关 + pending 请求管理（全局 INCR 序列防碰撞，per-object 单 active）。
对应 docs/10 §8。无 HTTP/WS 依赖，便于单测。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. V1.1 M13 创建 takeover service：开关 / open_pending（INCR+单active）/ resolve / list / clear
"""
import time

from redis.asyncio import Redis

_K_ENABLED = "mychat:takeover:enabled:{oid}"      # String "1"，存在即开启
_K_PENDING = "mychat:takeover:pending:{oid}:{pid}"  # HASH {user_text, created_ts, object_id, status}
_K_PENDING_SEQ = "mychat:takeover:pending_seq"    # 全局 INCR 序列（防同毫秒撞）
_K_ACTIVE = "mychat:takeover:active:{oid}"        # String，当前 active pending_id（per-object 单 active）

PENDING_TTL = 120   # 待答超时秒数


async def is_takeover_enabled(redis: Redis, oid: str) -> bool:
    return await redis.get(_K_ENABLED.format(oid=oid)) == "1"


async def set_takeover_enabled(redis: Redis, oid: str, enabled: bool) -> None:
    key = _K_ENABLED.format(oid=oid)
    if enabled:
        await redis.set(key, "1")
    else:
        await redis.delete(key)


async def open_takeover_request(redis: Redis, oid: str, user_text: str) -> str:
    """生成 pending（per-object 单 active：新请求覆盖旧 active）。返回 pending_id。"""
    pid_seq = await redis.incr(_K_PENDING_SEQ)
    pending_id = f"takeover_{pid_seq}"
    ts = int(time.time() * 1000)
    key = _K_PENDING.format(oid=oid, pid=pending_id)
    await redis.hset(key, mapping={
        "user_text": user_text, "created_ts": ts,
        "object_id": oid, "status": "pending",
    })
    await redis.expire(key, PENDING_TTL)
    await redis.set(_K_ACTIVE.format(oid=oid), pending_id)
    return pending_id


async def get_active_pending(redis: Redis, oid: str) -> str | None:
    v = await redis.get(_K_ACTIVE.format(oid=oid))
    return v.decode() if isinstance(v, bytes) else v


async def resolve_takeover_answer(redis: Redis, oid: str, pending_id: str, answer: str) -> dict | None:
    """校验 pending 存在 + object_id 匹配 + 是当前 active。返回 {user_text, answer} 或 None。"""
    key = _K_PENDING.format(oid=oid, pid=pending_id)
    if not await redis.exists(key):
        return None
    data = await redis.hgetall(key)

    def gv(field):
        v = data.get(field, data.get(field.encode()))
        return v.decode() if isinstance(v, bytes) else v

    if gv("object_id") != oid:
        return None
    if await get_active_pending(redis, oid) != pending_id:
        return None   # 非当前 active（已被新请求覆盖）
    return {"user_text": gv("user_text") or "", "answer": answer}


async def clear_pending(redis: Redis, oid: str, pending_id: str) -> None:
    await redis.delete(_K_PENDING.format(oid=oid, pid=pending_id))
    if await get_active_pending(redis, oid) == pending_id:
        await redis.delete(_K_ACTIVE.format(oid=oid))


async def list_pending(redis: Redis) -> list[dict]:
    """列出所有未决代答请求（SCAN pending:*）"""
    out = []
    async for k in redis.scan_iter(match="mychat:takeover:pending:*"):
        kk = k.decode() if isinstance(k, bytes) else k
        data = await redis.hgetall(k)

        def gv(field):
            v = data.get(field, data.get(field.encode()))
            return v.decode() if isinstance(v, bytes) else v

        out.append({
            "pending_id": kk.rsplit(":", 1)[-1],
            "object_id": gv("object_id"),
            "user_text": gv("user_text"),
            "created_ts": gv("created_ts"),
        })
    return out
