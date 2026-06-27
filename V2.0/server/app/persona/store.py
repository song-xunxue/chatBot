"""
人设存储(Redis + 文件双写 CRUD)
Redis 为权威源,启动时从文件重建索引;写入顺序 Redis→文件,文件失败仅告警。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 persona store 到 V2.0(零业务改动;含 snapshot/rollback 反推快照为 M3 预留)
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
_K_DEFAULT = "mychat:persona:_default_id"  # String 默认人设 id(避开 mychat:persona:{pid})
_K_BIND = "mychat:obj:{oid}:persona"       # String 对象→人设绑定
_K_VERSION = "mychat:persona_version:{pid}"  # 单调递增版本号计数器(INCR)

_MAX_HISTORY = 20   # history 最多保留快照数

# 文件目录(基于项目根的绝对路径,避免依赖运行时 cwd)
_DATA_DIR = PROJECT_ROOT / "server" / "data"
_PERSONA_DIR = PROJECT_ROOT / settings.persona_dir


def _persona_file(pid: str) -> Path:
    return _PERSONA_DIR / f"{pid}.json"


async def get_persona(redis: Redis, persona_id: str) -> PersonaCard | None:
    """按 id 取人设;不存在返回 None"""
    raw = await redis.get(_K_PERSONA.format(pid=persona_id))
    if not raw:
        return None
    return PersonaCard.from_dict(json.loads(raw))


async def set_persona(redis: Redis, card: PersonaCard) -> None:
    """写入人设:Redis(SET + SADD index) + 文件双写(文件失败仅告警)"""
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
    """删除人设:Redis(DEL + SREM) + 删文件。返回是否曾存在"""
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
    """列出所有人设(pipeline 批量读取,顺带清理 index 中已不存在的脏 id)"""
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
    """取默认人设:读 mychat:persona:_default_id,不存在则用 seed 落库"""
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
    """取对象绑定的人设 id,未绑定返回默认(persona_active_id)"""
    pid = await redis.get(_K_BIND.format(oid=object_id))
    return pid or settings.persona_active_id or "default"


async def bind_object_persona(redis: Redis, object_id: str, persona_id: str) -> None:
    """绑定人设到聊天对象"""
    await redis.set(_K_BIND.format(oid=object_id), persona_id)


async def save_avatar(redis: Redis, persona_id: str, file_bytes: bytes, ext: str) -> str:
    """保存头像/人设图到 server/data/static/avatar/,返回相对路径并更新人设 avatar"""
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
    """导出为 persona_*.json 兼容格式(嵌套 prompts 形态)。
    inner 含 profile/preferences/relationship/example_dialogue 新字段,
    同时写入 data 顶层与 data.prompts.<id>.data(保证 importer 扁平分支可读)。"""
    card = await get_persona(redis, persona_id)
    if not card:
        return None
    d = card.to_dict()
    inner = {
        "name": d["name"], "description": d["description"],
        "personality": d["personality"], "scenario": d["scenario"],
        "creator_notes": d["creator_notes"],
        "profile": d.get("profile", {}),
        "preferences": d.get("preferences", {}),
        "relationship": d.get("relationship", {}),
        "example_dialogue": d.get("example_dialogue", []),
    }
    return {
        "spec": "chara_card_v2",
        "data": {
            **inner,
            "prompts": {d["id"]: {"name": d["name"], "data": inner}},
        },
    }


async def snapshot_persona(redis: Redis, persona_id: str) -> int:
    """快照当前人设入 card.history,返回新 version_no。
    用于反推合并前留底,使合并可回滚。history 元素精简平铺(去 history/images 防写放大)。"""
    card = await get_persona(redis, persona_id)
    if not card:
        return 0
    version_no = await redis.incr(_K_VERSION.format(pid=persona_id))
    snap = {k: v for k, v in card.to_dict().items() if k not in ("history", "images")}
    snap["_version_no"] = version_no
    card.history.append(snap)
    if len(card.history) > _MAX_HISTORY:
        card.history = card.history[-_MAX_HISTORY:]
    await set_persona(redis, card)
    return version_no


async def rollback_persona(redis: Redis, persona_id: str, version_no: int) -> PersonaCard | None:
    """回滚到指定 version_no 的快照。
    回滚前先 snapshot 当前卡(保证回滚可再回滚);version 不存在返回 None。"""
    card = await get_persona(redis, persona_id)
    if not card:
        return None
    target = next((s for s in card.history if s.get("_version_no") == version_no), None)
    if target is None:
        return None
    # 先快照当前卡留底
    await snapshot_persona(redis, persona_id)
    latest = await get_persona(redis, persona_id)   # 含本次 snapshot 的 history 链
    # 用 target 恢复字段(去掉内部 _ 前缀键)
    restore = {k: v for k, v in target.items() if not k.startswith("_")}
    restored = PersonaCard.from_dict(restore)
    restored.id = persona_id
    restored.history = latest.history if latest else []
    await set_persona(redis, restored)
    return restored


async def init_default_if_absent(redis: Redis) -> None:
    """启动时确保默认人设存在(应用 lifespan 调用)"""
    await get_default_persona(redis)
