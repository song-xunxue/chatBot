"""
人设 REST 接口
人设 CRUD / 导入 / 导出 / 头像上传 / 模型绑定 / 对象绑定。
复用 ws.py 同款 access_token 鉴权（Header X-Access-Token 或 query token）。
对应 docs/09 §6.1。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 创建人设 REST 接口
"""
import json
import re
import time

from fastapi import APIRouter, HTTPException, UploadFile, File, Header, Query, Depends

from storage.redis_client import get_redis
from persona import store
from persona.models import PersonaCard, ModelBinding
from persona.importer import parse_persona_json
from core.config import settings

router = APIRouter(prefix="/api/v1", tags=["persona"])


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖：Header 或 query 任一通过即可；显式拒绝空 token（防误配开放）"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


def _new_id(name: str) -> str:
    """为新人设生成 id（优先用 name slug，回退时间戳）"""
    slug = re.sub(r"[^\w一-龥-]", "", name or "")[:32]
    return slug or f"persona_{int(time.time() * 1000)}"


@router.get("/persona", dependencies=[Depends(_auth)])
async def list_personas():
    """列出所有人设"""
    redis = await get_redis()
    return [c.to_dict() for c in await store.list_personas(redis)]


@router.post("/persona", dependencies=[Depends(_auth)])
async def create_persona(body: dict):
    """创建人设（body 为 PersonaCard 字段 dict，自动生成 id）"""
    card = PersonaCard.from_dict(body)
    if not card.id:
        card.id = _new_id(card.name)
    redis = await get_redis()
    await store.set_persona(redis, card)
    return card.to_dict()


@router.get("/persona/{persona_id}", dependencies=[Depends(_auth)])
async def get_persona(persona_id: str):
    """获取单个人设"""
    redis = await get_redis()
    card = await store.get_persona(redis, persona_id)
    if not card:
        raise HTTPException(status_code=404, detail="persona not found")
    return card.to_dict()


@router.put("/persona/{persona_id}", dependencies=[Depends(_auth)])
async def update_persona(persona_id: str, body: dict):
    """更新人设（全量替换，id 以路径为准）"""
    card = PersonaCard.from_dict(body)
    card.id = persona_id
    redis = await get_redis()
    await store.set_persona(redis, card)
    return card.to_dict()


@router.delete("/persona/{persona_id}", dependencies=[Depends(_auth)])
async def delete_persona(persona_id: str):
    """删除人设"""
    redis = await get_redis()
    existed = await store.delete_persona(redis, persona_id)
    return {"deleted": existed}


@router.post("/persona/import", dependencies=[Depends(_auth)])
async def import_persona(file: UploadFile = File(...)):
    """导入 persona_*.json（兼容嵌套/扁平两形态）"""
    data = await file.read()
    if len(data) > 1_048_576:  # 1MB 上限，防 DoS
        raise HTTPException(status_code=413, detail="persona file too large")
    try:
        raw = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="invalid persona json")
    card = parse_persona_json(raw)
    redis = await get_redis()
    await store.set_persona(redis, card)
    return card.to_dict()


@router.get("/persona/{persona_id}/export", dependencies=[Depends(_auth)])
async def export_persona(persona_id: str):
    """导出为 persona_*.json 兼容格式"""
    redis = await get_redis()
    data = await store.export_persona(redis, persona_id)
    if data is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return data


@router.post("/persona/{persona_id}/avatar", dependencies=[Depends(_auth)])
async def upload_avatar(persona_id: str, file: UploadFile = File(...)):
    """上传头像/人设图"""
    redis = await get_redis()
    if not await store.get_persona(redis, persona_id):
        raise HTTPException(status_code=404, detail="persona not found")
    ext = (file.filename or "jpg").rsplit(".", 1)[-1].lower()
    rel = await store.save_avatar(redis, persona_id, await file.read(), ext)
    return {"avatar": rel}


@router.put("/persona/{persona_id}/model", dependencies=[Depends(_auth)])
async def bind_model(persona_id: str, body: dict):
    """绑定 provider+model+params"""
    redis = await get_redis()
    card = await store.get_persona(redis, persona_id)
    if not card:
        raise HTTPException(status_code=404, detail="persona not found")
    card.model = ModelBinding(
        provider=body.get("provider", "glm"),
        model=body.get("model", ""),
        params=body.get("params", {}) or {},
    )
    await store.set_persona(redis, card)
    return card.to_dict()


@router.post("/persona/{persona_id}/bind/{object_id}", dependencies=[Depends(_auth)])
async def bind_object(persona_id: str, object_id: str):
    """绑定人设到聊天对象"""
    redis = await get_redis()
    if not await store.get_persona(redis, persona_id):
        raise HTTPException(status_code=404, detail="persona not found")
    await store.bind_object_persona(redis, object_id, persona_id)
    return {"object_id": object_id, "persona_id": persona_id}
