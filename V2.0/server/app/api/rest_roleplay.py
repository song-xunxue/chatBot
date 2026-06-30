"""
roleplay 训练样本 REST 接口(M8):录/批量录/列/改/删(→neg)。
对应 docs/02 §12.3。鉴权 verify_token。底层 chat_store roleplay block 三层(物理隔离,不进 get_history)。

路由(prefix /api/v1):
  POST   /roleplay/{oid}/messages        录单条 {role, content}
  POST   /roleplay/{oid}/messages/batch  批量录连发 {items:[{role,content}]}
  GET    /roleplay/{oid}/messages        列样本(完整字段)
  PUT    /roleplay/{oid}/messages/{mid}  改单条 {content}
  DELETE /roleplay/{oid}/messages/{mid}  删单条(→neg 队列)

作者: 李文煜
日期: 2026-06-30
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from api._auth import verify_token
from core.config import settings
from storage.redis_client import get_redis
from storage import chat_store

router = APIRouter(prefix="/api/v1", tags=["roleplay"])

_VALID_ROLES = ("user", "assistant", "system")


@router.post("/roleplay/{oid}/messages", dependencies=[Depends(verify_token)])
async def add_message(oid: str, body: dict = Body(default={})):
    """录单条 roleplay 样本。body: {role: user|assistant|system, content}"""
    role = body.get("role", "user")
    content = (body.get("content") or "").strip()
    if role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {_VALID_ROLES}")
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    redis = await get_redis()
    mid = await chat_store.append_roleplay_message(redis, oid, role=role, content=content)
    return {"mid": mid}


@router.post("/roleplay/{oid}/messages/batch", dependencies=[Depends(verify_token)])
async def add_batch(oid: str, body: dict = Body(default={})):
    """批量录 roleplay(同 open block 连发)。body: {items:[{role, content}]}。受 takeover_batch_max 截断。"""
    items = body.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="items required")
    for it in items:
        if it.get("role") not in _VALID_ROLES or not (it.get("content") or "").strip():
            raise HTTPException(status_code=400, detail="each item needs valid role and content")
    items = items[:settings.takeover_batch_max]
    redis = await get_redis()
    mids = await chat_store.append_roleplay_batch(redis, oid, items=items)
    return {"mids": mids, "count": len(mids)}


@router.get("/roleplay/{oid}/messages", dependencies=[Depends(verify_token)])
async def list_messages(oid: str, limit: int = Query(default=1000, ge=1, le=5000)):
    """列 roleplay 样本(跨 block,按 ts 正序,完整字段含 role/content/mid)"""
    redis = await get_redis()
    return {"object_id": oid, "messages": await chat_store.list_roleplay(redis, oid, limit=limit)}


@router.put("/roleplay/{oid}/messages/{mid}", dependencies=[Depends(verify_token)])
async def update_message(oid: str, mid: str, body: dict = Body(default={})):
    """改单条 roleplay 内容(→ status=edited)。body: {content}"""
    content = body.get("content")
    if content is None:
        raise HTTPException(status_code=400, detail="content required")
    redis = await get_redis()
    hit = await chat_store.update_roleplay(redis, oid, mid, content)
    if not hit:
        raise HTTPException(status_code=404, detail="message not found")
    return {"updated": True}


@router.delete("/roleplay/{oid}/messages/{mid}", dependencies=[Depends(verify_token)])
async def delete_message(oid: str, mid: str):
    """删单条 roleplay(→neg 队列作训练负信号,物理删)"""
    redis = await get_redis()
    hit = await chat_store.delete_roleplay(redis, oid, mid)
    if not hit:
        raise HTTPException(status_code=404, detail="message not found")
    return {"deleted": True}
