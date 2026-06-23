"""
人设存储（Redis + 文件双写 CRUD）
Redis 为权威源，启动时从文件重建索引；写入顺序 Redis→文件，文件失败仅告警。
对应 docs/04 §3.2、docs/09 §3.3。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 创建 persona store：get/set/delete/list/default/bind/avatar/export
"""
import json
import logging
import time
from pathlib import Path

from redis.asyncio import Redis

from persona.models import PersonaCard
from persona.default import default_persona
from core.config import settings, PROJECT_ROOT

logger = logging.getLogger(__name__)

# Redis 键
_K_PERSONA = "mychat:persona:{pid}"       # String(JSON) 人设完整 JSON
_K_INDEX = "mychat:persona:index"          # Set 所有人设 id
_K_DEFAULT = "mychat:persona:_default_id"  # String 默认人设 id（避开 mychat:persona:{pid}）
_K_BIND = "mychat:obj:{oid}:persona"       # String 对象→人设绑定

# 文件目录（基于项目根的绝对路径，避免依赖运行时 cwd）
_DATA_DIR = PROJECT_ROOT / "server" / "data"
_PERSONA_DIR = PROJECT_ROOT / settings.persona_dir


def _persona_file(pid: str) -> Path:
    return _PERSONA_DIR / f"{pid}.json"


async def get_persona(redis: Redis, persona_id: str) -> PersonaCard | None:
    """按 id 取人设；不存在返回 None"""
    raw = await redis.get(_K_PERSONA.format(pid=persona_id))
    if not raw:
        return None
    return PersonaCard.from_dict(json.loads(raw))


async def set_persona(redis: Redis, card: PersonaCard) -> None:
    """写入人设：Redis(SET + SADD index) + 文件双写（文件失败仅告警）"""
    card.updated_ts = int(time.time() * 1000)
    payload = json.dumps(card.to_dict(), ensure_ascii=False)
    await redis.set(_K_PERSONA.format(pid=card.id), payload)
    await redis.sadd(_K_INDEX, card.id)
    try:
        _PERSONA_DIR.mkdir(parents=True, exist_ok=True)
        _persona_file(card.id).write_text(payload, encoding="utf-8")
    except OSError as e:
        logger.warning("persona 文件双写失败 id=%s: %s", card.id, e)


async def delete_persona(redis: Redis, persona_id: str) -> bool:
    """删除人设：Redis(DEL + SREM) + 删文件。返回是否曾存在"""
    existed = bool(await redis.exists(_K_PERSONA.format(pid=persona_id)))
    await redis.delete(_K_PERSONA.format(pid=persona_id))
    await redis.srem(_K_INDEX, persona_id)
    f = _persona_file(persona_id)
    if f.exists():
        try:
            f.unlink()
        except OSError as e:
            logger.warning("persona 文件删除失败 id=%s: %s", persona_id, e)
    return existed


async def list_personas(redis: Redis) -> list[PersonaCard]:
    """列出所有人设（pipeline 批量读取，顺带清理 index 中已不存在的脏 id）"""
    ids = await redis.smembers(_K_INDEX)
    if not ids:
        return []
    pipe = redis.pipeline()
    for pid in ids:
        pipe.get(_K_PERSONA.format(pid=pid))
    raws = await pipe.execute()
    cards = []
    for pid, raw in zip(ids, raws):
        if not raw:
            await redis.srem(_K_INDEX, pid)  # 脏 id 惰性清理
            continue
        cards.append(PersonaCard.from_dict(json.loads(raw)))
    return cards


async def get_default_persona(redis: Redis) -> PersonaCard:
    """取默认人设：读 mychat:persona:default，不存在则用 seed 落库"""
    pid = await redis.get(_K_DEFAULT)
    if pid:
        card = await get_persona(redis, pid)
        if card:
            return card
    card = default_persona()
    await set_persona(redis, card)
    await redis.set(_K_DEFAULT, card.id)
    return card


async def get_object_persona_id(redis: Redis, object_id: str) -> str:
    """取对象绑定的人设 id，未绑定返回默认（persona_active_id）"""
    pid = await redis.get(_K_BIND.format(oid=object_id))
    return pid or settings.persona_active_id or "default"


async def bind_object_persona(redis: Redis, object_id: str, persona_id: str) -> None:
    """绑定人设到聊天对象"""
    await redis.set(_K_BIND.format(oid=object_id), persona_id)


async def save_avatar(redis: Redis, persona_id: str, file_bytes: bytes, ext: str) -> str:
    """保存头像/人设图到 server/data/static/avatar/，返回相对路径并更新人设 avatar"""
    rel = f"static/avatar/{persona_id}.{ext.lstrip('.')}"
    abs_path = _DATA_DIR / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(file_bytes)
    card = await get_persona(redis, persona_id)
    if card:
        card.avatar = rel
        await set_persona(redis, card)
    return rel


async def export_persona(redis: Redis, persona_id: str) -> dict | None:
    """导出为 persona_*.json 兼容格式（嵌套 prompts 形态）"""
    card = await get_persona(redis, persona_id)
    if not card:
        return None
    d = card.to_dict()
    inner = {
        "name": d["name"], "description": d["description"],
        "personality": d["personality"], "scenario": d["scenario"],
        "creator_notes": d["creator_notes"],
    }
    return {
        "spec": "chara_card_v2",
        "data": {
            **inner,
            "prompts": {d["id"]: {"name": d["name"], "data": inner}},
        },
    }


async def init_default_if_absent(redis: Redis) -> None:
    """启动时确保默认人设存在（应用 lifespan 调用）"""
    await get_default_persona(redis)
