"""
代人聊天代答 pending 队列存储(per-object FIFO,替代 V1.0 单 active 覆盖)
V2.0 原创,对应 docs/02 §8.2。纯存储层(无业务编排/无 QQ 下发,下发在 takeover/service.py)。

键设计(docs/02 §8.2):
  mychat:takeover:enabled:{oid}        String "1"  存在即开启代答模式
  mychat:takeover:queue:{oid}          List        per-object pending_id FIFO(RPUSH 入队 / LREM 出队)
  mychat:takeover:pending:{oid}:{pid}  Hash        待答详情 {pid,user_text,created_ts,object_id,status,msg_id,...}
  mychat:takeover:pid:seq              INCR        全局序生成 pid(防同毫秒撞)
  mychat:takeover:msgseq:{oid}         INCR        per-oid 发送序(防 QQ 同 msg_id+msg_seq 去重)

行为:
  - enqueue:INCR pid → 写 pending Hash(EXPIRE TTL) → RPUSH 入队 → 返回 pid
  - resolve:校验 pending 存在 + object_id 匹配 → 从队列 LREM 移除该 pid → 返回 pending;
    pending 过期(TTL)成孤儿时,list_queue/resolve 惰性清理(扫描上限 takeover_queue_orphan_scan_limit)
  - 队首消费:resolve(pid=None) 先清孤儿头再取 LINDEX 0;管理员跳序答指定 pid 用 LREM 精确移除

V1.0 用单 active(SET 覆盖),管理员连发代答只留最后一条;V2.0 改 FIFO 队列"不丢"。

作者: 李文煜
日期: 2026-06-30

2026-06-30
变更说明：
  1. M8 新建 takeover_store:per-object FIFO 队列(替 V1.0 单 active 覆盖丢消息)
     + 孤儿 pid 惰性清理(pending TTL 过期)+ msgseq per-oid 防 QQ 去重

2026-09-07
变更说明：
  1. 新增 drain_queue:出队全部 pending(手动回复消化/一键清空用)——逐条标记 status+LREM
     (非 DEL 整键,处理期间新入队不受影响);跳过并发已被 resolve/skip 消费的(status!=pending),
     防同一 pending 双重落库
  2. 新增 skip_mark(跳过保留 Hash 1h 审计,归档失败可恢复)/ requeue(drain 回灌兜底,
     手动回复全链失败时待答消息不丢)
"""
import json
import time

from redis.asyncio import Redis

from core.config import settings

_K_ENABLED = "mychat:takeover:enabled:{oid}"
_K_QUEUE = "mychat:takeover:queue:{oid}"
_K_PENDING = "mychat:takeover:pending:{oid}:{pid}"
_K_PID_SEQ = "mychat:takeover:pid:seq"
_K_MSGSEQ = "mychat:takeover:msgseq:{oid}"


def _now_ms() -> int:
    """当前毫秒时间戳"""
    return int(time.time() * 1000)


# ================ 代答开关 ================

async def is_enabled(redis: Redis, oid: str) -> bool:
    """代答模式是否开启(键存在即开启)"""
    return await redis.get(_K_ENABLED.format(oid=oid)) == "1"


async def set_enabled(redis: Redis, oid: str, enabled: bool) -> None:
    """开/关代答模式。关闭时只删开关键,不动 pending 队列(已入队仍可代答清空)。"""
    key = _K_ENABLED.format(oid=oid)
    if enabled:
        await redis.set(key, "1")
    else:
        await redis.delete(key)


# ================ pending 队列 ================

async def enqueue(redis: Redis, oid: str, *, user_text: str, msg_id: str = "") -> str:
    """生成 pending(INCR 全局序)+ 写 pending Hash(EXPIRE TTL)+ RPUSH 入队。返回 pid。
    webhook 代答模式开启时调:用户消息入队等管理员代答(不进 pipeline)。"""
    seq = await redis.incr(_K_PID_SEQ)
    pid = f"takeover_{seq}"
    ts = _now_ms()
    key = _K_PENDING.format(oid=oid, pid=pid)
    pipe = redis.pipeline()
    pipe.hset(key, mapping={
        "pid": pid,
        "user_text": user_text,
        "created_ts": ts,
        "object_id": oid,
        "status": "pending",
        "msg_id": msg_id,           # 用户消息 id(被动回复用,60min 窗口)
    })
    pipe.expire(key, settings.takeover_pending_ttl_sec)
    pipe.rpush(_K_QUEUE.format(oid=oid), pid)
    await pipe.execute()
    return pid


async def get_pending(redis: Redis, oid: str, pid: str) -> dict | None:
    """取单条 pending 详情(过期/不存在返回 None)"""
    raw = await redis.hgetall(_K_PENDING.format(oid=oid, pid=pid))
    return raw or None


async def list_queue(redis: Redis, oid: str) -> list[dict]:
    """列 per-object pending 队列(FIFO 正序,队首在前),带孤儿过滤。
    pending 过期(TTL)的 pid 惰性 LREM 移除(不阻断列表返回)。"""
    queue_key = _K_QUEUE.format(oid=oid)
    pids = await redis.lrange(queue_key, 0, -1)
    if not pids:
        return []
    out: list[dict] = []
    orphans: list[str] = []
    for pid in pids:
        pending = await redis.hgetall(_K_PENDING.format(oid=oid, pid=pid))
        if not pending:
            orphans.append(pid)         # TTL 过期孤儿,待清理
            continue
        out.append(pending)
    if orphans:                         # 惰性清理孤儿 pid(从队列移除)
        pipe = redis.pipeline()
        for pid in orphans:
            pipe.lrem(queue_key, 1, pid)
        await pipe.execute()
    return out


async def queue_length(redis: Redis, oid: str) -> int:
    """队列长度(含潜在孤儿,快速计数,面板状态用)"""
    return await redis.llen(_K_QUEUE.format(oid=oid))


async def _purge_orphan_head(redis: Redis, oid: str) -> None:
    """清理队首连续的孤儿 pid(已过期),最多扫 takeover_queue_orphan_scan_limit 个。
    供 resolve/skip 队首消费前调,确保取到活 pending。"""
    queue_key = _K_QUEUE.format(oid=oid)
    for _ in range(settings.takeover_queue_orphan_scan_limit):
        head = await redis.lindex(queue_key, 0)
        if head is None:
            return                     # 队列空
        if await redis.exists(_K_PENDING.format(oid=oid, pid=head)):
            return                     # 队首是活 pending,停止清理
        await redis.lpop(queue_key)    # 队首孤儿,弹出丢弃


async def resolve(redis: Redis, oid: str, pid: str | None = None) -> dict | None:
    """出队一条 pending 供代答。pid=None 取队首(先清孤儿头);指定 pid 用 LREM 精确移除。
    校验 pending 存在 + object_id 匹配;命中回写 status=resolved + 续期 1h(供审计),返回 pending。
    过期/不匹配/空队列返回 None。"""
    queue_key = _K_QUEUE.format(oid=oid)
    if pid is None:
        await _purge_orphan_head(redis, oid)              # 队首孤儿先清,确保取到活 pending
        pid = await redis.lindex(queue_key, 0)
        if pid is None:
            return None                 # 空队列
    pending = await redis.hgetall(_K_PENDING.format(oid=oid, pid=pid))
    if not pending:
        await redis.lrem(queue_key, 1, pid)   # 指定 pid 已过期成孤儿:清掉返 None
        return None
    if pending.get("object_id") != oid:
        return None                     # object_id 不匹配(异常态)
    pending_key = _K_PENDING.format(oid=oid, pid=pid)
    pipe = redis.pipeline()
    pipe.hset(pending_key, mapping={"status": "resolved"})
    pipe.expire(pending_key, 3600)      # 续期 1h 供审计/重试
    pipe.lrem(queue_key, 1, pid)        # 出队(指定 pid 或已解析的队首 pid,统一 LREM)
    await pipe.execute()
    pending["status"] = "resolved"      # 回填返回 dict(pending 是 hgetall 旧快照,读时 status 还是 pending)
    return pending


async def skip(redis: Redis, oid: str, pid: str | None = None) -> bool:
    """跳过(放弃代答):出队 + 删 pending。pid=None 跳队首(先清孤儿)。命中返回 True。"""
    queue_key = _K_QUEUE.format(oid=oid)
    if pid is None:
        await _purge_orphan_head(redis, oid)
        pid = await redis.lindex(queue_key, 0)
        if pid is None:
            return False
    existed = await redis.exists(_K_PENDING.format(oid=oid, pid=pid))
    pipe = redis.pipeline()
    pipe.delete(_K_PENDING.format(oid=oid, pid=pid))
    pipe.lrem(queue_key, 1, pid)
    await pipe.execute()
    return bool(existed)


async def drain_queue(redis: Redis, oid: str, *, status: str = "manual") -> list[dict]:
    """出队全部 pending 并返回详情(FIFO 正序)。2026-09-07 手动回复消化队列/面板一键清空共用。
    快照 pids 后逐条处理(标记 status+续期 1h 审计+LREM 出队,同 resolve 审计语义)——
    逐条而非 DEL 整键:处理期间的新入队不受影响;已过期孤儿直接 LREM 丢弃;
    跳过 status!=pending 的(并发已被 resolve/skip 消费,防同一 pending 双重落库)。"""
    queue_key = _K_QUEUE.format(oid=oid)
    pids = await redis.lrange(queue_key, 0, -1)
    out: list[dict] = []
    for pid in pids:
        pending_key = _K_PENDING.format(oid=oid, pid=pid)
        pending = await redis.hgetall(pending_key)
        pipe = redis.pipeline()
        if pending and pending.get("status") == "pending":
            pipe.hset(pending_key, "status", status)
            pipe.expire(pending_key, 3600)   # 审计续期 1h(同 resolve)
            pending["status"] = status       # 回填返回 dict
            out.append(pending)
        pipe.lrem(queue_key, 1, pid)         # 活 pending 出队/孤儿清理,统一 LREM
        await pipe.execute()
    return out


async def skip_mark(redis: Redis, oid: str, pid: str | None = None, *,
                    status: str = "skipped") -> bool:
    """跳过但保留 pending Hash 1h 审计(2026-09-07):status!=pending 视为已被并发消费返 False,
    命中则标记 status+续期 1h+LREM 出队(不 DEL——归档失败时待答详情留存可人工恢复)。
    skip_and_archive 用(先原子占位再归档)。pid=None 跳队首(先清孤儿,同 skip)。"""
    queue_key = _K_QUEUE.format(oid=oid)
    if pid is None:
        await _purge_orphan_head(redis, oid)
        pid = await redis.lindex(queue_key, 0)
        if pid is None:
            return False
    pending_key = _K_PENDING.format(oid=oid, pid=pid)
    pending = await redis.hgetall(pending_key)
    if not pending or pending.get("status") != "pending":
        await redis.lrem(queue_key, 1, pid)   # 已被 resolve/drain 消费或孤儿:仅清出队
        return False
    pipe = redis.pipeline()
    pipe.hset(pending_key, "status", status)
    pipe.expire(pending_key, 3600)            # 审计续期 1h(归档失败可人工恢复)
    pipe.lrem(queue_key, 1, pid)
    await pipe.execute()
    return True


async def requeue(redis: Redis, oid: str, pendings: list[dict]) -> int:
    """把 drain 出的 pending 回灌队列(2026-09-07 降级兜底):status 重置 pending + RPUSH
    保原 FIFO 顺序。手动回复副作用链与降级归档都失败时调,待答消息不丢(可再代答/清空)。"""
    n = 0
    for p in pendings:
        pid = p.get("pid")
        if not pid:
            continue
        key = _K_PENDING.format(oid=oid, pid=pid)
        await redis.hset(key, "status", "pending")
        await redis.rpush(_K_QUEUE.format(oid=oid), pid)
        n += 1
    return n


# ================ 交付状态(代答下发后回写)================

async def mark_delivered(redis: Redis, oid: str, pid: str, deliver: dict) -> None:
    """回写 pending 交付状态:delivered(0/1)/ deliver_mode(passive/active/"")。供面板展示/重试。"""
    key = _K_PENDING.format(oid=oid, pid=pid)
    if not await redis.exists(key):
        return
    await redis.hset(key, mapping={
        "delivered": "1" if deliver.get("delivered") else "0",
        "deliver_mode": deliver.get("mode", ""),
    })


async def next_msg_seq(redis: Redis, oid: str) -> int:
    """取下一个 per-oid 发送序(INCR,防 QQ 同 msg_id+msg_seq 重复被拒)。批量连发逐条递增。"""
    return await redis.incr(_K_MSGSEQ.format(oid=oid))


# ================ 代答 TTS 开关(M-tts,2026-08-04)================
# 两开关(逻辑同 tts_reply 插件):enable=代答是否启用语音;send_text_also=启用时是否同发文本(默认 False 只语音)
# voice/speed/gain/emotion 复用 tts_reply 插件 config(同一 bot 音色),本处仅存代答专属两开关
_K_TTS = "mychat:takeover:tts:{oid}"


async def get_tts_config(redis: Redis, oid: str) -> dict:
    """代答 TTS 配置 {enable, send_text_also};未设置返空 dict(等价 enable=False,纯文本代答)"""
    raw = await redis.get(_K_TTS.format(oid=oid))
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def set_tts_config(redis: Redis, oid: str, enable: bool, send_text_also: bool) -> None:
    """写代答 TTS 配置(整 JSON 替换)"""
    await redis.set(
        _K_TTS.format(oid=oid),
        json.dumps({"enable": bool(enable), "send_text_also": bool(send_text_also)}, ensure_ascii=False),
    )
