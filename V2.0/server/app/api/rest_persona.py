"""
人设管理 REST 接口(M7):CRUD + 导入/导出 + 模型绑定 + 快照/回滚。
复用 persona/store.py + importer.parse_persona_json。鉴权 X-Access-Token。

路由(prefix /api/v1):
  GET    /persona                       列所有人设
  GET    /persona/{pid}                 取单个
  POST   /persona                       新建(body = PersonaCard dict)
  PUT    /persona/{pid}                 更新(合并现有 + body 覆盖)
  DELETE /persona/{pid}                 删除(Redis + 文件)
  POST   /persona/import                导入(FormData persona_*.json,兼容嵌套/扁平两形态)
  GET    /persona/{pid}/export          导出(嵌套 prompts 形态)
  PUT    /persona/{pid}/model           绑定模型(provider/model/params)
  POST   /persona/{pid}/snapshot        快照(反推前留底,返回 version_no)
  POST   /persona/{pid}/rollback        回滚到指定 version_no

作者: 李文煜
日期: 2026-06-30
"""
import json

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from api._auth import verify_token
from storage.redis_client import get_redis
from persona import store as persona_store
from persona.models import PersonaCard

router = APIRouter(prefix="/api/v1", tags=["persona"])


@router.get("/persona", dependencies=[Depends(verify_token)])
async def list_personas():
    redis = await get_redis()
    return [c.to_dict() for c in await persona_store.list_personas(redis)]


@router.get("/persona/{pid}", dependencies=[Depends(verify_token)])
async def get_persona(pid: str):
    redis = await get_redis()
    card = await persona_store.get_persona(redis, pid)
    if card is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return card.to_dict()


@router.post("/persona", dependencies=[Depends(verify_token)])
async def create_persona(body: dict):
    redis = await get_redis()
    card = PersonaCard.from_dict(body)
    if not card.id:
        raise HTTPException(status_code=400, detail="persona id required")
    await persona_store.set_persona(redis, card)
    return card.to_dict()


@router.put("/persona/{pid}", dependencies=[Depends(verify_token)])
async def update_persona(pid: str, body: dict):
    """更新:现有字段 + body 覆盖(保留 id)"""
    redis = await get_redis()
    existing = await persona_store.get_persona(redis, pid)
    if existing is None:
        raise HTTPException(status_code=404, detail="persona not found")
    merged = existing.to_dict()
    merged.update(body)
    merged["id"] = pid
    card = PersonaCard.from_dict(merged)
    await persona_store.set_persona(redis, card)
    return card.to_dict()


@router.delete("/persona/{pid}", dependencies=[Depends(verify_token)])
async def delete_persona(pid: str):
    redis = await get_redis()
    existed = await persona_store.delete_persona(redis, pid)
    if not existed:
        raise HTTPException(status_code=404, detail="persona not found")
    return {"deleted": True, "id": pid}


@router.post("/persona/import", dependencies=[Depends(verify_token)])
async def import_persona(file: UploadFile = File(...)):
    """导入 persona_*.json(importer.parse_persona_json 兼容嵌套/扁平两形态)"""
    from persona.importer import parse_persona_json
    raw = await file.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"invalid json: {e}")
    pid = (data.get("data", {}).get("id") if isinstance(data.get("data"), dict) else "") \
        or data.get("id", "") or ""
    card = parse_persona_json(data, pid)
    if not card.id:
        raise HTTPException(status_code=400, detail="parse failed: no id")
    redis = await get_redis()
    await persona_store.set_persona(redis, card)
    return card.to_dict()


@router.get("/persona/{pid}/export", dependencies=[Depends(verify_token)])
async def export_persona(pid: str):
    redis = await get_redis()
    data = await persona_store.export_persona(redis, pid)
    if data is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return data


@router.put("/persona/{pid}/model", dependencies=[Depends(verify_token)])
async def bind_model(pid: str, body: dict = Body(default={})):
    """绑定模型(provider/model/params)"""
    redis = await get_redis()
    card = await persona_store.get_persona(redis, pid)
    if card is None:
        raise HTTPException(status_code=404, detail="persona not found")
    if "provider" in body:
        card.model.provider = body["provider"]
    if "model" in body:
        card.model.model = body["model"]
    if "params" in body:
        card.model.params = body["params"] or {}
    await persona_store.set_persona(redis, card)
    return {"id": pid, "model": {"provider": card.model.provider,
                                  "model": card.model.model, "params": card.model.params}}


@router.post("/persona/{pid}/snapshot", dependencies=[Depends(verify_token)])
async def snapshot(pid: str):
    """快照当前人设(反推前留底)。返回新 version_no"""
    redis = await get_redis()
    version_no = await persona_store.snapshot_persona(redis, pid)
    if version_no == 0:
        raise HTTPException(status_code=404, detail="persona not found")
    return {"id": pid, "version_no": version_no}


@router.post("/persona/{pid}/rollback", dependencies=[Depends(verify_token)])
async def rollback(pid: str, body: dict = Body(default={})):
    """回滚到指定 version_no。body: {version_no: int}"""
    if "version_no" not in body:
        raise HTTPException(status_code=400, detail="version_no required")
    try:
        version_no = int(body["version_no"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="version_no must be int")
    redis = await get_redis()
    card = await persona_store.rollback_persona(redis, pid, version_no)
    if card is None:
        raise HTTPException(status_code=404, detail="persona or version not found")
    return card.to_dict()
