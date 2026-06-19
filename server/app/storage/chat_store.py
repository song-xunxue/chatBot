"""
对话历史存储（Redis）
按 object_id（聊天对象）存消息列表（Redis List 结构），用途：
  1. 拼装 LLM 上下文（get_history 取最近 N 条）
  2. 客户端历史同步（M5 增量同步的数据源）
M2 阶段实现追加 / 取历史 / 清空。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.3 创建 chat_store：append_message / get_history / clear_history
"""
import json

from redis.asyncio import Redis

from llm.base import Message


def _key(object_id: str) -> str:
    """Redis 键命名：chat:<object_id>"""
    return f"chat:{object_id}"


async def append_message(redis: Redis, object_id: str, role: str, content: str) -> None:
    """追加一条消息到对话历史（JSON 序列化后 rpush 到 List 尾部，保持时序）"""
    msg = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    await redis.rpush(_key(object_id), msg)


async def get_history(redis: Redis, object_id: str, limit: int = 20) -> list[Message]:
    """取最近 limit 条历史消息（时间正序），转为 Message 列表供 LLM 拼上下文"""
    # lrange 负索引取最后 limit 条
    raw = await redis.lrange(_key(object_id), -limit, -1)
    messages = []
    for item in raw:
        data = json.loads(item)
        messages.append(Message(role=data["role"], content=data["content"]))
    return messages


async def clear_history(redis: Redis, object_id: str) -> None:
    """清空某对象的历史（对应需求 F-C-04「保存上限清理」）"""
    await redis.delete(_key(object_id))
