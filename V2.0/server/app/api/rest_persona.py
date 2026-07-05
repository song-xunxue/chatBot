"""
人设管理 REST 接口(M7):CRUD + 导入/导出 + 模型绑定 + 快照/回滚。
复用 persona/store.py + importer.parse_persona_json。鉴权 X-Access-Token。

路由(prefix /api/v1)—— 单人设简化(2026-07-04):只有 1 个人设,以后也是,去 create/delete/import:
  GET    /persona                       列所有人设(单人设下返回 1 条)
  GET    /persona/{pid}                 取单个
  PUT    /persona/{pid}                 更新(合并现有 + body 覆盖)
  GET    /persona/{pid}/export          导出(嵌套 prompts 形态)
  PUT    /persona/{pid}/model           绑定模型(provider/model/params)
  POST   /persona/{pid}/snapshot        快照(反推前留底,返回 version_no)
  POST   /persona/{pid}/rollback        回滚到指定 version_no

作者: 李文煜
日期: 2026-06-30
"""
from fastapi import APIRouter, Body, Depends, HTTPException

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


@router.get("/persona/{pid}/export", dependencies=[Depends(verify_token)])
async def export_persona(pid: str):
    redis = await get_redis()
    data = await persona_store.export_persona(redis, pid)
    if data is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return data


@router.put("/persona/{pid}/model", dependencies=[Depends(verify_token)])
async def bind_model(pid: str, body: dict = Body(default={})):
    """绑定模型(provider/model/params)。原子约束:model 必须与 provider 同时设定——
    孤立 model(provider 空)会打到全局 chat_provider 的别的厂商 API 导致报错(#6 写缝隙守不变量)。"""
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
    # 原子约束:合并后 model 非空必须带 provider(无论本次传入还是卡片已有),杜绝孤立 model
    if card.model.model and not card.model.provider:
        raise HTTPException(status_code=400,
                            detail="绑定 model 必须同时指定 provider(model 不能脱离 provider 单独存在)")
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
