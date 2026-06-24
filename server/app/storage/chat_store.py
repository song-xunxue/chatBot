"""
对话历史存储（Redis）
按 object_id（聊天对象）存消息列表（Redis List 结构），用途：
  1. 拼装 LLM 上下文（get_history 取最近 N 条）
  2. 客户端历史同步（M5 增量同步的数据源）
  3. M3 作为四级记忆的 Working 层（复用本 List）
M2 阶段实现追加 / 取历史 / 清空；M3.2 扩展可选字段并统一 mychat: 前缀。
V1.1 M11：新增 roleplay 正样本物理隔离存储（独立键，绝不污染 get_history/LLM 上下文）。
对应 docs/04 §3、docs/10 §6。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.3 创建 chat_store：append_message / get_history / clear_history

2026-06-23
变更说明：
  1. M3.2 append_message 新增可选 ts/msg_type/mid/source 字段（向后兼容）；键统一 mychat: 前缀

2026-06-24
变更说明：
  1. V1.1 M11 新增 roleplay 正样本存储：独立键 mychat:chat_roleplay:{oid}（物理隔离，get_history 不读），
     支持录/列/改/删；删除的对话写入 mychat:roleplay:neg:{oid} 作训练负样本。零侵入 V1.0 append/get_history。
"""
import json
import time
import uuid

from redis.asyncio import Redis

from llm.base import Message


def _key(object_id: str) -> str:
    """Redis 键命名：mychat:chat:<object_id>（统一 mychat: 前缀，对应 docs/04 §3）"""
    return f"mychat:chat:{object_id}"


# V1.1 M11：roleplay 正/负样本独立键（物理隔离，绝不与真实聊天混入 get_history）
def _roleplay_key(object_id: str) -> str:
    return f"mychat:chat_roleplay:{object_id}"


def _roleplay_neg_key(object_id: str) -> str:
    return f"mychat:roleplay:neg:{object_id}"


async def append_message(redis: Redis, object_id: str, role: str, content: str,
                         *, ts: int = 0, msg_type: str = "chat",
                         mid: str = "", source: str = "user_turn") -> None:
    """追加一条消息到对话历史（JSON 序列化后 rpush 到 List 尾部，保持时序）
    M3.2：新增可选 ts/msg_type/mid/source 字段（向后兼容，旧调用不受影响）"""
    ts = ts or int(time.time() * 1000)
    msg = json.dumps({"role": role, "content": content, "ts": ts,
                      "msg_type": msg_type, "mid": mid, "source": source},
                     ensure_ascii=False)
    await redis.rpush(_key(object_id), msg)


async def get_history(redis: Redis, object_id: str, limit: int = 20) -> list[Message]:
    """取最近 limit 条历史消息（时间正序），转为 Message 列表供 LLM 拼上下文
    仅取 role/content，忽略 ts 等附加字段（保持 Message 结构稳定）。
    注意：只读 mychat:chat:{oid}，不读 roleplay 正样本键（V1.1 M11 物理隔离）。"""
    raw = await redis.lrange(_key(object_id), -limit, -1)
    messages = []
    for item in raw:
        data = json.loads(item)
        messages.append(Message(role=data["role"], content=data["content"]))
    return messages


async def clear_history(redis: Redis, object_id: str) -> None:
    """清空某对象的历史（对应需求 F-C-04「保存上限清理」）"""
    await redis.delete(_key(object_id))


# —— V1.2 历史展示/编辑（含 ts/mid，区别 get_history 仅给 LLM role/content）——

async def list_messages(redis: Redis, object_id: str, limit: int = 500) -> list[dict]:
    """列历史消息（含 mid/ts/source）供历史页展示与编辑。
    mid 用 Redis List 绝对索引（稳定对应 List 位置，供 update/delete 定位）。"""
    total = await redis.llen(_key(object_id))
    start = max(0, total - limit)
    raw = await redis.lrange(_key(object_id), start, -1)
    out = []
    for i, item in enumerate(raw):
        d = json.loads(item)
        out.append({
            "mid": str(start + i),            # Redis List 绝对索引
            "role": d.get("role", ""),
            "content": d.get("content", ""),
            "ts": d.get("ts", 0),
            "source": d.get("source", ""),
        })
    return out


async def update_message(redis: Redis, object_id: str, mid: str, *,
                         role: str | None = None, content: str | None = None,
                         ts: int | None = None) -> bool:
    """按 mid（List 索引）改写一条历史消息的 role/content/ts（LSET 原地改，不改索引）。"""
    idx = int(mid)
    raw = await redis.lindex(_key(object_id), idx)
    if raw is None:
        return False
    d = json.loads(raw)
    if role is not None:
        d["role"] = role
    if content is not None:
        d["content"] = content
    if ts is not None:
        d["ts"] = ts
    await redis.lset(_key(object_id), idx, json.dumps(d, ensure_ascii=False))
    return True


async def delete_message(redis: Redis, object_id: str, mid: str) -> bool:
    """按 mid（List 索引）删除一条历史消息（LSET 标记 + LREM，删除后后面索引前移）。"""
    idx = int(mid)
    if await redis.lindex(_key(object_id), idx) is None:
        return False
    await redis.lset(_key(object_id), idx, "__TODELETE__")
    await redis.lrem(_key(object_id), 1, "__TODELETE__")
    return True


# —— V1.1 M11：roleplay 正样本存储（面板模拟训练）——

async def append_roleplay_pair(redis: Redis, object_id: str,
                               user_text: str, assistant_text: str) -> tuple:
    """录一对 user+assistant roleplay 正样本（同 ts，各自唯一 mid），返回 (mid_user, mid_assistant, ts)。
    写入独立键 mychat:chat_roleplay:{oid}，绝不污染 mychat:chat:{oid}（get_history 取不到）。"""
    ts = int(time.time() * 1000)
    mid_u = f"rp_{uuid.uuid4().hex[:12]}"
    mid_a = f"rp_{uuid.uuid4().hex[:12]}"
    msg_u = json.dumps({"role": "user", "content": user_text, "ts": ts,
                        "mid": mid_u, "source": "roleplay"}, ensure_ascii=False)
    msg_a = json.dumps({"role": "assistant", "content": assistant_text, "ts": ts,
                        "mid": mid_a, "source": "roleplay"}, ensure_ascii=False)
    pipe = redis.pipeline()
    pipe.rpush(_roleplay_key(object_id), msg_u)
    pipe.rpush(_roleplay_key(object_id), msg_a)
    await pipe.execute()
    return mid_u, mid_a, ts


async def append_roleplay_single(redis: Redis, object_id: str, role: str, content: str) -> tuple:
    """V1.2 录单条 roleplay 消息（不强制配对，支持连续多条同角色后再回复）。返回 (mid, ts)。"""
    mid = f"rp_{uuid.uuid4().hex[:12]}"
    ts = int(time.time() * 1000)
    msg = json.dumps({"role": role, "content": content, "ts": ts,
                      "mid": mid, "source": "roleplay"}, ensure_ascii=False)
    await redis.rpush(_roleplay_key(object_id), msg)
    return mid, ts


async def list_roleplay(redis: Redis, object_id: str, limit: int = 1000) -> list[dict]:
    """列 roleplay 正样本（带 mid，时间正序）"""
    raw = await redis.lrange(_roleplay_key(object_id), -limit, -1)
    return [json.loads(x) for x in raw]


async def update_roleplay(redis: Redis, object_id: str, mid: str, content: str) -> bool:
    """按 mid 改写单条 roleplay 正样本内容（重建 List）。返回是否命中。"""
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
    """按 mid 删除单条 roleplay 正样本，同时把该条写入 neg 队列作训练负样本（重建 List）。返回是否命中。"""
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


async def clear_roleplay(redis: Redis, object_id: str) -> None:
    """清空某对象的 roleplay 正样本（不动真实历史）"""
    await redis.delete(_roleplay_key(object_id))
