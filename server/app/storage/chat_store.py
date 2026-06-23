"""
对话历史存储（Redis）
按 object_id（聊天对象）存消息列表（Redis List 结构），用途：
  1. 拼装 LLM 上下文（get_history 取最近 N 条）
  2. 客户端历史同步（M5 增量同步的数据源）
  3. M3 作为四级记忆的 Working 层（复用本 List）
M2 阶段实现追加 / 取历史 / 清空；M3.2 扩展可选字段并统一 mychat: 前缀。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.3 创建 chat_store：append_message / get_history / clear_history

2026-06-23
变更说明：
  1. M3.2 append_message 新增可选 ts/msg_type/mid/source 字段（向后兼容）；键统一 mychat: 前缀
"""
import json
import time

from redis.asyncio import Redis

from llm.base import Message


def _key(object_id: str) -> str:
    """Redis 键命名：mychat:chat:<object_id>（统一 mychat: 前缀，对应 docs/04 §3）"""
    return f"mychat:chat:{object_id}"


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
    仅取 role/content，忽略 ts 等附加字段（保持 Message 结构稳定）"""
    raw = await redis.lrange(_key(object_id), -limit, -1)
    messages = []
    for item in raw:
        data = json.loads(item)
        messages.append(Message(role=data["role"], content=data["content"]))
    return messages


async def clear_history(redis: Redis, object_id: str) -> None:
    """清空某对象的历史（对应需求 F-C-04「保存上限清理」）"""
    await redis.delete(_key(object_id))
