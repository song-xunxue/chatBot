"""
聊天记录存储(block 三层结构,Redis)
V2.0 原创重写,对应 docs/02 §9(Redis 键)/§11(Python API)。

三层数据模型:会话(object_id) → blocks[](有序) → messages[](有序)。
  - Block:语义连续对话片段,静默超阈值(block_silence_min)或回合结束则关闭开新 block。
  - Message:mid 全局 UUID(弃 V1.0 List 索引),带 score 四元组字段(M3 评分填)。
  - roleplay 物理隔离:训练样本独立键,绝不进 get_history/LLM 上下文(守 V1.0 铁律)。

M2 实现:
  - live 走 block 三层(open_or_get_block/close_block/append_message/get_history/...)
  - roleplay 简化为独立 List(离散样本不需 block 分组,block 化留 M8)
  - set_score 预留(M3 评分系统调用,字段已在 append_message 留空)

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 重写 chat_store:扁平 List → block 三层(会话/blocks/messages)
     静默分组(block_silence_min)、UUID mid、get_history 只读真实键、roleplay 物理隔离

2026-06-30
变更说明：
  1. M7 新增 list_blocks(列会话所有 block 元数据 + msg_count,面板历史页 block 第一层浏览)

2026-06-30
变更说明：
  1. M8 roleplay 物理隔离从简化 List 升级为 block 三层(mychat:block_roleplay:* / mychat:msg_roleplay:*),
     与 live 结构对齐(独立前缀,get_history 只读 live 键天然隔离);
     新增 close_roleplay_block(手动分段)/ append_roleplay_batch(批量录连发);
     update/delete 从 O(N) 重建 List 改为 O(1) hset / ZREM+DEL;签名向后兼容(list_roleplay 返回含 content)

2026-07-03
变更说明：
  1. 新增 list_recent_sessions(跨 object_id 列最近活跃会话,SCAN blocks 键聚合 last_ts/block_count),
     供面板历史页自动展示会话列表(解决"看不到 openid"导致查不到历史)

2026-07-07
变更说明：
  1. list_recent_blocks 改混合:同时返回 chat 真实 block + roleplay 训练 block,加 source 字段
     (real/training)区分,供面板历史页混合展示(训练样本并入对话历史,拟人化一体体验)
"""
import json
import time
import uuid

from redis.asyncio import Redis

from llm.base import Message
from core.config import settings

# sender → LLM Message.role 映射(ai/proxy 都作 assistant 喂 LLM)
_SENDER_TO_ROLE = {
    "user": "user",
    "ai": "assistant",
    "proxy": "assistant",   # 代答人工产出,对 LLM 视作 assistant
    "system": "system",
}


def _now_ms() -> int:
    """当前毫秒时间戳"""
    return int(time.time() * 1000)


def _gen_id(prefix: str = "") -> str:
    """生成全局唯一 id(默认 UUID hex;可选前缀便于辨识)"""
    return f"{prefix}{uuid.uuid4().hex}" if prefix else uuid.uuid4().hex


# —— Redis 键构造(live 真实聊天走 block 三层)——
def _blocks_key(object_id: str) -> str:
    """会话所有 block 的索引(ZSet, score=start_ts, member=block_id)"""
    return f"mychat:chat:{object_id}:blocks"


def _block_key(block_id: str) -> str:
    """block 元数据(Hash)"""
    return f"mychat:block:{block_id}"


def _msgs_key(block_id: str) -> str:
    """block 内消息索引(ZSet, score=ts, member=mid)"""
    return f"mychat:block:{block_id}:msgs"


def _msg_key(mid: str) -> str:
    """消息详情(Hash)"""
    return f"mychat:msg:{mid}"


def _active_key(object_id: str) -> str:
    """当前 open block_id 缓存(String,加速判定,可由 blocks 尾部推导)"""
    return f"mychat:chat:{object_id}:active_block"


# —— roleplay 物理隔离键(block 三层,与 live 前缀独立;get_history 只读 live 键 → 天然隔离)——
def _rp_blocks_key(object_id: str) -> str:
    """roleplay 会话所有 block 的索引(ZSet, score=start_ts)"""
    return f"mychat:block_roleplay:{object_id}:blocks"


def _rp_block_key(block_id: str) -> str:
    """roleplay block 元数据(Hash)"""
    return f"mychat:block_roleplay:{block_id}"


def _rp_msgs_key(block_id: str) -> str:
    """roleplay block 内消息索引(ZSet, score=ts)"""
    return f"mychat:block_roleplay:{block_id}:msgs"


def _rp_msg_key(mid: str) -> str:
    """roleplay 消息详情(Hash)"""
    return f"mychat:msg_roleplay:{mid}"


def _rp_active_key(object_id: str) -> str:
    """当前 open roleplay block_id 缓存(String,加速判定)"""
    return f"mychat:roleplay:{object_id}:active_block"


def _roleplay_neg_key(object_id: str) -> str:
    """删除的 roleplay 样本(List,训练负样本信号,沿用 V1.0)"""
    return f"mychat:roleplay:neg:{object_id}"


# ================ Block 管理 ================

async def _new_block(redis: Redis, object_id: str, *, source: str = "live", ts: int = 0) -> dict:
    """新建一个 open block 并登记,返回 block dict"""
    ts = ts or _now_ms()
    block_id = _gen_id()
    block = {
        "block_id": block_id,
        "object_id": object_id,
        "start_ts": ts,
        "end_ts": ts,
        "status": "open",
        "source": source,
        "summary": "",
        "close_reason": "",
    }
    pipe = redis.pipeline()
    pipe.hset(_block_key(block_id), mapping=block)         # block 元数据
    pipe.zadd(_blocks_key(object_id), {block_id: ts})      # 会话 block 索引(按 start_ts 排序)
    pipe.set(_active_key(object_id), block_id)             # 缓存当前 open block
    await pipe.execute()
    return block


async def open_or_get_block(redis: Redis, object_id: str, *, source: str = "live") -> dict:
    """取当前 open block;若过期(静默超阈值)或不存在,close 旧的并开新 block。

    判定流程(docs/02 §6):
      1. 取 active block_id(无则开新);
      2. 读该 block 末条消息 ts(用 block.end_ts 近似),若 now - end_ts > block_silence_min → close 旧 block 开新;
      3. 否则返回当前 open block。
    """
    block_id = await redis.get(_active_key(object_id))
    if not block_id:
        return await _new_block(redis, object_id, source=source)
    block = await redis.hgetall(_block_key(block_id))
    if not block or block.get("status") != "open":
        # active 失效(被手动 close 或数据缺失),开新 block
        return await _new_block(redis, object_id, source=source)
    # 静默分组判定:当前时间与 block 末条 ts 之差超阈值 → 开新 block
    end_ts = int(block.get("end_ts", 0) or 0)
    if _now_ms() - end_ts > settings.block_silence_min * 60_000:
        await close_block(redis, block_id, reason="silence")
        return await _new_block(redis, object_id, source=source)
    return block


async def close_block(redis: Redis, block_id: str, *, reason: str = "silence") -> None:
    """关闭 block:回填 end_ts、status=closed、close_reason。
    summary 情景摘要编码留 M4 记忆融合钩子。"""
    block = await redis.hgetall(_block_key(block_id))
    if not block:
        return
    pipe = redis.pipeline()
    pipe.hset(_block_key(block_id), mapping={
        "status": "closed",
        "end_ts": _now_ms(),
        "close_reason": reason,
    })
    # 清 active 缓存(若该 block 正是 active);下次 open_or_get_block 会开新 block
    if block.get("object_id"):
        pipe.delete(_active_key(block["object_id"]))
    await pipe.execute()


# ================ Message 写 ================

async def append_message(redis: Redis, object_id: str, *,
                         sender: str, content: str, rich: str = "",
                         source: str = "live", ts: int = 0) -> str:
    """追加消息到当前 open block,生成全局 UUID mid,返回 mid。
    ai/proxy 消息的 score 四元组由调用方后续用 set_score 补(M3),此处留空。"""
    ts = ts or _now_ms()
    block = await open_or_get_block(redis, object_id, source=source)
    block_id = block["block_id"]
    mid = _gen_id()
    msg = {
        "mid": mid,
        "block_id": block_id,
        "object_id": object_id,
        "sender": sender,           # user/ai/proxy/system
        "content": content,
        "rich": rich,               # JSON 字符串(富内容,M6 多模态);空串表无
        "ts": ts,
        "source": source,           # live/roleplay/proxy/tool
        "status": "active",
        # score 四元组(M3 评分填,初始留空)
        "score_base": "",
        "mood_at_score": "",
        "mood_bias": "",
        "score": "",
        "score_note": "",   # 评分批注(2026-07-07,说明为什么这个分;手动改分填)
    }
    pipe = redis.pipeline()
    pipe.hset(_msg_key(mid), mapping=msg)            # 消息详情
    pipe.zadd(_msgs_key(block_id), {mid: ts})        # block 内消息索引(按 ts 排序)
    pipe.hset(_block_key(block_id), "end_ts", ts)    # 更新 block 末条 ts(静默分组依据)
    await pipe.execute()
    return mid


async def append_message_batch(redis: Redis, object_id: str, *, items: list[dict]) -> list[str]:
    """批量追加(连发场景:user 连发或代答连发),同一 open block,返回 mid 列表。
    items 每项为 {sender, content, rich?, source?, ts?}。"""
    mids: list[str] = []
    for item in items:
        mid = await append_message(
            redis, object_id,
            sender=item["sender"],
            content=item["content"],
            rich=item.get("rich", ""),
            source=item.get("source", "live"),
            ts=item.get("ts", 0),
        )
        mids.append(mid)
    return mids


# ================ Message 读 ================

async def get_history(redis: Redis, object_id: str, *,
                      max_blocks: int | None = None,
                      max_messages: int | None = None) -> list[Message]:
    """LLM 上下文:取最近 max_blocks 个 block 的最近 max_messages 条消息(时间正序),转 Message。
    只读真实聊天键(mychat:msg:*),绝不读 roleplay 隔离键;软删/撤回消息过滤。"""
    max_blocks = settings.chat_history_max_blocks if max_blocks is None else max_blocks
    max_messages = settings.chat_history_max_messages if max_messages is None else max_messages
    # 最近 max_blocks 个 block_id(blocks ZSet 按 start_ts 倒序取前 N,再转正序)
    block_ids = await redis.zrevrange(_blocks_key(object_id), 0, max_blocks - 1)
    if not block_ids:
        return []
    block_ids = list(reversed(block_ids))   # 旧→新
    # pipeline 批量取各 block 的 mid 列表
    pipe = redis.pipeline()
    for bid in block_ids:
        pipe.zrange(_msgs_key(bid), 0, -1)
    mid_groups = await pipe.execute()
    # 收集全部 mid(保留 block 顺序)
    all_mids: list[str] = []
    for group in mid_groups:
        all_mids.extend(group)
    if not all_mids:
        return []
    # pipeline 批量取消息详情
    pipe = redis.pipeline()
    for mid in all_mids:
        pipe.hgetall(_msg_key(mid))
    raws = await pipe.execute()
    # 过滤软删/撤回
    items = [r for r in raws if r and r.get("status", "active") not in ("deleted", "recalled")]
    if not items:
        return []
    # 按 ts 排序,取最近 max_messages 条
    items.sort(key=lambda d: int(d.get("ts", 0) or 0))
    items = items[-max_messages:]
    return [Message(role=_SENDER_TO_ROLE.get(d.get("sender", ""), "user"),
                    content=d.get("content", "")) for d in items]


async def list_messages(redis: Redis, object_id: str, *,
                        block_id: str | None = None, limit: int = 500) -> list[dict]:
    """列消息(完整字段含 score 四元组),供 Web 面板历史页(M7)。
    block_id 指定则只列该 block;否则列最近 limit 条(跨 block)。"""
    if block_id:
        mids = await redis.zrange(_msgs_key(block_id), 0, -1)
    else:
        # 取所有 block 的 mid,按 ts 排序后取最近 limit 条
        block_ids = await redis.zrange(_blocks_key(object_id), 0, -1)
        pipe = redis.pipeline()
        for bid in block_ids:
            pipe.zrange(_msgs_key(bid), 0, -1)
        groups = await pipe.execute()
        mids = [mid for g in groups for mid in g]
    if not mids:
        return []
    pipe = redis.pipeline()
    for mid in mids:
        pipe.hgetall(_msg_key(mid))
    raws = await pipe.execute()
    items = [r for r in raws if r]
    items.sort(key=lambda d: int(d.get("ts", 0) or 0))
    return items[-limit:]


async def list_blocks(redis: Redis, object_id: str, *, limit: int = 100) -> list[dict]:
    """列会话所有 block(含 status/时间/summary),按 start_ts 倒序(最近在前),供 Web 面板历史页(M7)。
    每块附 msg_count(block 内消息数)便于前端展示。无 block 返回空列表。"""
    block_ids = await redis.zrevrange(_blocks_key(object_id), 0, limit - 1)   # 倒序:最近在前
    if not block_ids:
        return []
    # pipeline 交替取 block 元数据 + 消息数(hgetall/zcard 配对,execute 返回扁平列表)
    pipe = redis.pipeline()
    for bid in block_ids:
        pipe.hgetall(_block_key(bid))
        pipe.zcard(_msgs_key(bid))
    raws = await pipe.execute()
    out = []
    for i in range(0, len(raws), 2):
        block = raws[i]
        if not block:
            continue
        block["msg_count"] = raws[i + 1] if i + 1 < len(raws) else 0
        out.append(block)
    return out


async def list_recent_sessions(redis: Redis, *, limit: int = 50) -> list[dict]:
    """列最近活跃会话(跨所有 object_id),按最近 block 的 start_ts 倒序,供面板自动展示(M7 改造)。
    SCAN mychat:chat:*:blocks 聚合:object_id + 最近 block 的 start_ts(作 last_ts 近似活跃度)+ block 总数。
    会话数少时 SCAN 安全;后续会话增长可改为 append_message 维护 sessions ZSet(本次不做)。无会话返回空列表。"""
    sessions: list[dict] = []
    async for raw_key in redis.scan_iter(match="mychat:chat:*:blocks", count=100):
        key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
        prefix, suffix = "mychat:chat:", ":blocks"
        if not (key.startswith(prefix) and key.endswith(suffix)):
            continue
        object_id = key[len(prefix):-len(suffix)]
        if not object_id:
            continue
        last = await redis.zrange(key, -1, -1, withscores=True)   # 末位 block_id + 其 start_ts(score)
        block_count = await redis.zcard(key)
        last_ts = int(last[0][1]) if last else 0
        sessions.append({"object_id": object_id, "last_ts": last_ts, "block_count": block_count})
    sessions.sort(key=lambda d: d["last_ts"], reverse=True)
    return sessions[:limit]


async def list_recent_blocks(redis: Redis, *, limit: int = 50) -> list[dict]:
    """列最近活跃 block(chat 真实 + roleplay 训练混合,按 start_ts 倒序),供面板历史页混合展示(2026-07-07 拟人化)。
    每条带 source 字段(real=真实对话/training=训练样本)区分来源;单用户场景:block=一段会话或一段训练样本。
    SCAN chat:*:blocks + block_roleplay:*:blocks 收集 (start_ts, block_id, object_id, source),
    合并取最近 limit,pipeline 按 source 用对应键补元数据+msg_count。无 block 返回空列表。"""
    # 1. SCAN chat + roleplay 的 blocks ZSet,收集 (start_ts, block_id, object_id, source)
    entries: list[tuple[int, str, str, str]] = []
    # chat 真实对话
    async for raw_key in redis.scan_iter(match="mychat:chat:*:blocks", count=100):
        key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
        prefix, suffix = "mychat:chat:", ":blocks"
        if not (key.startswith(prefix) and key.endswith(suffix)):
            continue
        object_id = key[len(prefix):-len(suffix)]
        if not object_id:
            continue
        for bid, ts in await redis.zrange(key, 0, -1, withscores=True):
            bid_s = bid.decode() if isinstance(bid, bytes) else bid
            entries.append((int(ts), bid_s, object_id, "real"))
    # roleplay 训练样本(物理隔离键,前缀独立)
    async for raw_key in redis.scan_iter(match="mychat:block_roleplay:*:blocks", count=100):
        key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
        prefix, suffix = "mychat:block_roleplay:", ":blocks"
        if not (key.startswith(prefix) and key.endswith(suffix)):
            continue
        object_id = key[len(prefix):-len(suffix)]
        if not object_id:
            continue
        for bid, ts in await redis.zrange(key, 0, -1, withscores=True):
            bid_s = bid.decode() if isinstance(bid, bytes) else bid
            entries.append((int(ts), bid_s, object_id, "training"))
    if not entries:
        return []
    # 2. 按 start_ts 倒序取最近 limit 个(混合排序)
    entries.sort(key=lambda e: e[0], reverse=True)
    entries = entries[:limit]
    # 3. pipeline 补 block 元数据 + msg_count(按 source 用不同键:chat _block_key/_msgs_key,roleplay _rp_*)
    pipe = redis.pipeline()
    for _ts, bid, _oid, src in entries:
        if src == "training":
            pipe.hgetall(_rp_block_key(bid))
            pipe.zcard(_rp_msgs_key(bid))
        else:
            pipe.hgetall(_block_key(bid))
            pipe.zcard(_msgs_key(bid))
    raws = await pipe.execute()
    out = []
    for i, (_ts, bid, oid, src) in enumerate(entries):
        block = raws[i * 2]
        if not block:
            continue
        count = raws[i * 2 + 1] if i * 2 + 1 < len(raws) else 0
        out.append({
            "block_id": bid,
            "object_id": oid,
            "start_ts": int(block.get("start_ts", 0) or 0),
            "end_ts": int(block.get("end_ts", 0) or 0),
            "status": block.get("status", ""),
            "msg_count": count,
            "source": src,
        })
    return out


async def get_message(redis: Redis, mid: str) -> dict | None:
    """按 mid 取单条(全局 UUID,稳定外键)"""
    raw = await redis.hgetall(_msg_key(mid))
    return raw or None


async def count_messages(redis: Redis, object_id: str) -> int:
    """统计某会话所有 block 的消息总数(跨 block 求和,供记忆 turn_count 用)。
    不等长对话下 //2 仅为近似轮数,episodic 阈值触发够用。"""
    block_ids = await redis.zrange(_blocks_key(object_id), 0, -1)
    if not block_ids:
        return 0
    pipe = redis.pipeline()
    for bid in block_ids:
        pipe.zcard(_msgs_key(bid))
    return sum(await pipe.execute())


# ================ Message 改 / 删 ================

async def update_message(redis: Redis, mid: str, *,
                         content: str | None = None, sender: str | None = None) -> bool:
    """改消息内容/sender(改 → status=edited)。命中返回 True。"""
    if not await redis.exists(_msg_key(mid)):
        return False
    mapping: dict = {"status": "edited"}
    if content is not None:
        mapping["content"] = content
    if sender is not None:
        mapping["sender"] = sender
    await redis.hset(_msg_key(mid), mapping=mapping)
    return True


async def delete_message(redis: Redis, mid: str, *, reason: str = "out_of_character") -> bool:
    """软删消息:status=deleted + delete_reason,保留供人格负样本(不物理删)。命中返回 True。"""
    if not await redis.exists(_msg_key(mid)):
        return False
    await redis.hset(_msg_key(mid), mapping={"status": "deleted", "delete_reason": reason})
    return True


async def delete_block(redis: Redis, block_id: str) -> dict:
    """物理删单个 block + 其全部消息(2026-07-05 会话整体删除)。
    删前联动:sender∈(ai,proxy) 且有 score 的消息写 score neg 队列(保留反推训练价值,清理不浪费样本)。
    物理删:block Hash + msgs ZSet + 各 msg Hash + 从会话 blocks ZSet 移除;若该 block 是 active 一并清。
    返回 {deleted_msgs, neg_linked}。block 不存在返回 {deleted_msgs:0, neg_linked:0}。"""
    block = await redis.hgetall(_block_key(block_id))
    if not block:
        return {"deleted_msgs": 0, "neg_linked": 0}
    object_id = block.get("object_id", "")
    mids = await redis.zrange(_msgs_key(block_id), 0, -1)
    neg_linked = 0
    # 删前联动 neg(软失败:记样本失败不阻塞删除)
    for mid in mids:
        msg = await redis.hgetall(_msg_key(mid))
        if not msg:
            continue
        if msg.get("sender") in ("ai", "proxy"):
            raw_score = msg.get("score", "")
            if raw_score not in ("", None):
                try:
                    score_val = int(float(raw_score))
                    from score import service as score_service
                    await score_service.record_negative_sample(
                        redis, object_id, mid, msg.get("content", ""), score_val)
                    neg_linked += 1
                except Exception:
                    pass   # 联动 neg 软失败(类型/服务异常),不阻塞物理删
    # 物理删(block + msgs 索引 + 各 msg + 从 blocks ZSet 移除)
    pipe = redis.pipeline()
    for mid in mids:
        pipe.delete(_msg_key(mid))
    pipe.delete(_msgs_key(block_id))
    pipe.delete(_block_key(block_id))
    if object_id:
        pipe.zrem(_blocks_key(object_id), block_id)
    await pipe.execute()
    # 若该 block 正是 active 缓存,清掉(下次消息进来开新 block)
    if object_id:
        active = await redis.get(_active_key(object_id))
        if active == block_id:
            await redis.delete(_active_key(object_id))
    return {"deleted_msgs": len(mids), "neg_linked": neg_linked}


async def delete_object_history(redis: Redis, object_id: str) -> dict:
    """物理删该 object_id 的全部历史(所有 block + 消息,2026-07-05 清空全部)。
    逐 block 调 delete_block(各自联动 neg),最后兜底清 blocks ZSet + active 缓存。
    返回 {deleted_blocks, deleted_msgs, neg_linked}。无历史返回全 0。"""
    block_ids = await redis.zrange(_blocks_key(object_id), 0, -1)
    deleted_msgs = 0
    neg_linked = 0
    for bid in block_ids:
        r = await delete_block(redis, bid)
        deleted_msgs += r["deleted_msgs"]
        neg_linked += r["neg_linked"]
    # 兜底:确保 blocks ZSet 与 active 完全清空(delete_block 已逐个 zrem,此处保险)
    pipe = redis.pipeline()
    pipe.delete(_blocks_key(object_id))
    pipe.delete(_active_key(object_id))
    await pipe.execute()
    return {"deleted_blocks": len(block_ids), "deleted_msgs": deleted_msgs, "neg_linked": neg_linked}


# ================ 评分(M3 调用,M2 预留)=================

async def set_score(redis: Redis, mid: str, *,
                    score_base: int, mood_value: float, mood_bias: float,
                    score_note: str | None = None) -> dict:
    """写入 score 四元组(score 由 score.quad.compute_quad 计算,公式收口于彼,架构 #2)。
    score_note(可选,2026-07-07):评分批注,非 None 时一并写入。返回完整四元组。消息不存在返 {}。"""
    if not await redis.exists(_msg_key(mid)):
        return {}
    from score.quad import compute_quad   # 公式唯一来源;lazy import 避免 storage↔score 导入环
    quad = compute_quad(score_base, mood_value, mood_bias)
    mapping = dict(quad)
    if score_note is not None:
        mapping["score_note"] = score_note
    await redis.hset(_msg_key(mid), mapping=mapping)
    return quad


# ================ roleplay 物理隔离(block 三层,M8 升级自简化 List)=================
# 训练样本离散录入,不按静默超时关 block:单一持续 open block 追加,close_roleplay_block 手动分段。
# 键前缀 mychat:block_roleplay:* / mychat:msg_roleplay:* 独立于 live,get_history 只读 live 键 → 天然隔离。

async def _rp_new_block(redis: Redis, object_id: str, *, ts: int = 0) -> dict:
    """新建 open roleplay block 并登记,返回 block dict"""
    ts = ts or _now_ms()
    block_id = _gen_id()
    block = {
        "block_id": block_id,
        "object_id": object_id,
        "start_ts": ts,
        "end_ts": ts,
        "status": "open",
        "source": "roleplay",
        "summary": "",
        "close_reason": "",
    }
    pipe = redis.pipeline()
    pipe.hset(_rp_block_key(block_id), mapping=block)
    pipe.zadd(_rp_blocks_key(object_id), {block_id: ts})
    pipe.set(_rp_active_key(object_id), block_id)
    await pipe.execute()
    return block


async def _rp_open_or_get_block(redis: Redis, object_id: str) -> dict:
    """取当前 open roleplay block;无/已关则开新(不做静默超时判定,训练样本离散录入)。"""
    block_id = await redis.get(_rp_active_key(object_id))
    if block_id:
        block = await redis.hgetall(_rp_block_key(block_id))
        if block and block.get("status") == "open":
            return block
    return await _rp_new_block(redis, object_id)


async def close_roleplay_block(redis: Redis, object_id: str, *, reason: str = "manual") -> None:
    """手动关闭当前 open roleplay block(分段用,如"第一幕/第二幕")。无 active 则空操作。"""
    block_id = await redis.get(_rp_active_key(object_id))
    if not block_id:
        return
    pipe = redis.pipeline()
    pipe.hset(_rp_block_key(block_id), mapping={
        "status": "closed", "end_ts": _now_ms(), "close_reason": reason})
    pipe.delete(_rp_active_key(object_id))
    await pipe.execute()


async def append_roleplay_message(redis: Redis, object_id: str, *,
                                  role: str, content: str, ts: int = 0,
                                  score_base: int | None = None) -> str:
    """录单条 roleplay 训练样本(独立 block 三层,绝不污染 get_history)。
    落当前 open roleplay block;返回 mid(rp_ 前缀便于辨识)。
    score_base(可选,2026-07-05,assistant 角色回复评分):非 None 时写 msg.score_base/score
    (roleplay 不走心情,score 直接=score_base)+ 按 classify 阈值联动 score 正/负样本队列(驱动反推,
    与 live 评分机制一致;reverse_infer 只读队列故零改动)。"""
    ts = ts or _now_ms()
    block = await _rp_open_or_get_block(redis, object_id)
    block_id = block["block_id"]
    mid = _gen_id("rp_")
    msg: dict = {
        "mid": mid,
        "block_id": block_id,
        "object_id": object_id,
        "role": role,            # user/assistant/system(roleplay 概念,独立于 live 的 sender)
        "content": content,
        "ts": ts,
        "source": "roleplay",
        "status": "active",
    }
    if score_base is not None:
        score_base = max(0, min(100, int(round(score_base))))
        msg["score_base"] = str(score_base)
        msg["score"] = str(score_base)   # roleplay 无 mood_bias,score 直接=score_base
    pipe = redis.pipeline()
    pipe.hset(_rp_msg_key(mid), mapping=msg)
    pipe.zadd(_rp_msgs_key(block_id), {mid: ts})
    pipe.hset(_rp_block_key(block_id), "end_ts", ts)
    await pipe.execute()
    # 联动反推样本队列(仅 assistant 评分才有反推意义;软失败不阻塞录入)
    if score_base is not None and role == "assistant":
        from score import service as score_service
        try:
            await score_service.record_score_sample(
                redis, object_id, mid, content, score_base)
        except Exception:
            pass
    return mid


async def append_roleplay_batch(redis: Redis, object_id: str, *, items: list[dict]) -> list[str]:
    """批量录 roleplay(同一 open block,连发场景)。items 每项 {role, content, ts?, score_base?}。返回 mid 列表。"""
    mids: list[str] = []
    for item in items:
        mid = await append_roleplay_message(
            redis, object_id,
            role=item["role"], content=item["content"], ts=item.get("ts", 0),
            score_base=item.get("score_base"))
        mids.append(mid)
    return mids


async def list_roleplay(redis: Redis, object_id: str, *,
                        block_id: str | None = None, limit: int = 1000) -> list[dict]:
    """列 roleplay 样本(按 ts 正序)。block_id 指定只列该会话;否则跨所有 block。取最近 limit 条。
    完整字段含 role/content/mid/score(2026-07-05 加)。"""
    if block_id:
        block_ids = [block_id]
    else:
        block_ids = await redis.zrange(_rp_blocks_key(object_id), 0, -1)
    if not block_ids:
        return []
    pipe = redis.pipeline()
    for bid in block_ids:
        pipe.zrange(_rp_msgs_key(bid), 0, -1)
    groups = await pipe.execute()
    mids = [mid for g in groups for mid in g]
    if not mids:
        return []
    pipe = redis.pipeline()
    for mid in mids:
        pipe.hgetall(_rp_msg_key(mid))
    raws = await pipe.execute()
    items = [r for r in raws if r]
    items.sort(key=lambda d: int(d.get("ts", 0) or 0))
    return items[-limit:]


async def update_roleplay(redis: Redis, object_id: str, mid: str, content: str) -> bool:
    """按 mid 改单条 roleplay 内容(msg Hash 直接 hset,O(1),→ status=edited)。命中返回 True。"""
    if not await redis.exists(_rp_msg_key(mid)):
        return False
    await redis.hset(_rp_msg_key(mid), mapping={"content": content, "status": "edited"})
    return True


async def delete_roleplay(redis: Redis, object_id: str, mid: str) -> bool:
    """按 mid 删单条 roleplay 样本(物理删:ZREM 出 block + DEL msg Hash)+ 写 roleplay neg 队列(训练负信号)
    + 清 score 正/负样本队列里该 mid 的样本(2026-07-05,评分联动过的删后不应再驱动反推)。命中返回 True。"""
    msg = await redis.hgetall(_rp_msg_key(mid))
    if not msg:
        return False
    pipe = redis.pipeline()
    bid = msg.get("block_id", "")
    if bid:
        pipe.zrem(_rp_msgs_key(bid), mid)
    pipe.delete(_rp_msg_key(mid))
    pipe.rpush(_roleplay_neg_key(object_id), json.dumps(
        {"text": msg.get("content", ""), "mid": mid, "ts": msg.get("ts", 0),
         "role": msg.get("role", ""), "reason": "roleplay_deleted"}, ensure_ascii=False))
    await pipe.execute()
    # 清 score 样本队列里该 mid 的样本(评分联动过的 assistant 回复删后不残留)
    from score import service as score_service
    try:
        await score_service.remove_sample_by_mid(redis, object_id, mid)
    except Exception:
        pass
    return True


async def new_roleplay_block(redis: Redis, object_id: str) -> dict:
    """新建会话(2026-07-05 多会话管理):关闭当前 open roleplay block(若有)+ 开新 open block。
    返回新 block dict。前端"新建会话"调,使后续录入落到新会话段。"""
    active = await redis.get(_rp_active_key(object_id))
    if active:
        await close_roleplay_block(redis, object_id, reason="new_session")
    return await _rp_new_block(redis, object_id)


async def list_roleplay_blocks(redis: Redis, object_id: str, *, limit: int = 100) -> list[dict]:
    """列 roleplay 会话(各 block 元数据 + msg_count,按 start_ts 倒序),供面板训练样本页左栏(2026-07-05)。
    每段 block = 一个训练会话。无会话返回空列表。"""
    block_ids = await redis.zrevrange(_rp_blocks_key(object_id), 0, limit - 1)
    if not block_ids:
        return []
    pipe = redis.pipeline()
    for bid in block_ids:
        pipe.hgetall(_rp_block_key(bid))
        pipe.zcard(_rp_msgs_key(bid))
    raws = await pipe.execute()
    out = []
    for i in range(0, len(raws), 2):
        block = raws[i]
        if not block:
            continue
        block["msg_count"] = raws[i + 1] if i + 1 < len(raws) else 0
        out.append(block)
    return out


async def set_roleplay_score(redis: Redis, object_id: str, mid: str, score_base: int) -> dict | None:
    """改 roleplay 消息评分(2026-07-05):重写 msg.score_base/score + 调整 score 样本队列
    (先 remove 旧样本,再按新分归类记录,驱动反推)。消息不存在返回 None。"""
    if not await redis.exists(_rp_msg_key(mid)):
        return None
    score_base = max(0, min(100, int(round(score_base))))
    await redis.hset(_rp_msg_key(mid), mapping={"score_base": str(score_base), "score": str(score_base)})
    msg = await redis.hgetall(_rp_msg_key(mid))
    role = msg.get("role", "")
    content = msg.get("content", "")
    from score import service as score_service
    try:
        await score_service.remove_sample_by_mid(redis, object_id, mid)
        if role == "assistant":
            await score_service.record_score_sample(redis, object_id, mid, content, score_base)
    except Exception:
        pass
    return {"mid": mid, "score_base": score_base, "score": score_base}


async def delete_roleplay_block(redis: Redis, block_id: str) -> dict:
    """物理删单个 roleplay 会话(block + 其全部消息,2026-07-06 训练样本删会话)。
    删前清各消息在 score 样本队列的样本(评分联动过的清掉,避免脏反推数据)。
    返回 {deleted_msgs}。block 不存在返回 {deleted_msgs:0}。"""
    block = await redis.hgetall(_rp_block_key(block_id))
    if not block:
        return {"deleted_msgs": 0}
    object_id = block.get("object_id", "")
    mids = await redis.zrange(_rp_msgs_key(block_id), 0, -1)
    # 清各消息的 score 样本(评分联动过的 assistant 回复删后不残留驱动反推)
    from score import service as score_service
    for mid in mids:
        try:
            await score_service.remove_sample_by_mid(redis, object_id, mid)
        except Exception:
            pass
    # 物理删(block + msgs 索引 + 各 msg + 从 blocks ZSet 移除)
    pipe = redis.pipeline()
    for mid in mids:
        pipe.delete(_rp_msg_key(mid))
    pipe.delete(_rp_msgs_key(block_id))
    pipe.delete(_rp_block_key(block_id))
    if object_id:
        pipe.zrem(_rp_blocks_key(object_id), block_id)
    await pipe.execute()
    # 若该 block 正是 active,清掉(下次录入开新会话)
    if object_id:
        active = await redis.get(_rp_active_key(object_id))
        if active == block_id:
            await redis.delete(_rp_active_key(object_id))
    return {"deleted_msgs": len(mids)}
