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


# —— roleplay 物理隔离键(简化为独立 List,M8 可 block 化)——
def _roleplay_key(object_id: str) -> str:
    """roleplay 正样本(List)"""
    return f"mychat:chat_roleplay:{object_id}"


def _roleplay_neg_key(object_id: str) -> str:
    """删除的 roleplay 样本(List,训练负样本信号)"""
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


# ================ 评分(M3 调用,M2 预留)=================

async def set_score(redis: Redis, mid: str, *,
                    score_base: int, mood_value: float, mood_bias: float) -> dict:
    """写入 score 四元组:mood_at_score=mood_value,score=clamp(round(score_base+mood_bias),0,100)。
    返回完整四元组,供反推判断(M3)。仅 ai/proxy 消息应调用。"""
    if not await redis.exists(_msg_key(mid)):
        return {}
    score = max(0, min(100, round(score_base + mood_bias)))
    quad = {
        "score_base": score_base,
        "mood_at_score": mood_value,
        "mood_bias": mood_bias,
        "score": score,
    }
    await redis.hset(_msg_key(mid), mapping=quad)
    return quad


# ================ roleplay 物理隔离(简化 List,M8 可 block 化)=================

async def append_roleplay_message(redis: Redis, object_id: str, *,
                                  role: str, content: str) -> str:
    """录单条 roleplay 训练样本(独立键 mychat:chat_roleplay:{oid},绝不污染 get_history)。
    返回 mid(rp_ 前缀便于辨识)。"""
    ts = _now_ms()
    mid = _gen_id("rp_")
    msg = json.dumps({"role": role, "content": content, "ts": ts,
                      "mid": mid, "source": "roleplay"}, ensure_ascii=False)
    await redis.rpush(_roleplay_key(object_id), msg)
    return mid


async def list_roleplay(redis: Redis, object_id: str, *, limit: int = 1000) -> list[dict]:
    """列 roleplay 正样本(带 mid,时间正序)"""
    raw = await redis.lrange(_roleplay_key(object_id), -limit, -1)
    return [json.loads(x) for x in raw]


async def update_roleplay(redis: Redis, object_id: str, mid: str, content: str) -> bool:
    """按 mid 改单条 roleplay 内容(重建 List)。返回是否命中。"""
    raw = await redis.lrange(_roleplay_key(object_id), 0, -1)
    hit = False
    new_items = []
    for x in raw:
        d = json.loads(x)
        if d.get("mid") == mid:
            d["content"] = content
            hit = True
        new_items.append(json.dumps(d, ensure_ascii=False))
    if hit:
        pipe = redis.pipeline()
        pipe.delete(_roleplay_key(object_id))
        for it in new_items:
            pipe.rpush(_roleplay_key(object_id), it)
        await pipe.execute()
    return hit


async def delete_roleplay(redis: Redis, object_id: str, mid: str) -> bool:
    """按 mid 删单条 roleplay 样本,同时写入 neg 队列作训练负样本(重建 List)。返回是否命中。"""
    raw = await redis.lrange(_roleplay_key(object_id), 0, -1)
    hit = False
    new_items = []
    deleted = None
    for x in raw:
        d = json.loads(x)
        if d.get("mid") == mid:
            hit = True
            deleted = d
            continue
        new_items.append(x)   # 未删的保留原 json 串
    if hit:
        pipe = redis.pipeline()
        pipe.delete(_roleplay_key(object_id))
        for it in new_items:
            pipe.rpush(_roleplay_key(object_id), it)
        if deleted:
            pipe.rpush(_roleplay_neg_key(object_id), json.dumps(
                {"text": deleted.get("content", ""), "mid": mid,
                 "ts": deleted.get("ts", 0), "reason": "roleplay_deleted"},
                ensure_ascii=False))
        await pipe.execute()
    return hit
