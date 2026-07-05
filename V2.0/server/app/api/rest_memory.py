"""
记忆系统 REST 接口(M4)
查看(core/episodic/long_term,可按 category 过滤)/ 统计 / 手动遗忘 / 恢复 / 锁定 / 批量遗忘。
鉴权 X-Access-Token(Header 或 query)。对应 docs/02 §6.2 / V1.0 rest_memory,M7 面板消费。

路由(prefix /api/v1):
  GET    /memory/{oid}?layer=&category=&limit=   查看记忆(层可选 core/episodic/long_term/all)
  GET    /memory/{oid}/stats                     各层数量 + 遗忘数
  DELETE /memory/{oid}/{mid}                     手动遗忘单条(可恢复)
  POST   /memory/{oid}/{mid}/restore             恢复已遗忘
  POST   /memory/{oid}/{mid}/lock                锁定/解锁(防遗忘)
  POST   /memory/{oid}/forget                    批量遗忘(body: category?/keyword?)

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M4 新建 rest_memory:查看/统计/手动遗忘/恢复/锁定/批量遗忘
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from core.config import settings
from storage.redis_client import get_redis
from api._auth import verify_token
from memory import store

router = APIRouter(prefix="/api/v1", tags=["memory"])


@router.get("/memory/{object_id}", dependencies=[Depends(verify_token)])
async def view_memory(object_id: str,
                      layer: str = Query(default="all"),
                      category: str = Query(default=""),
                      limit: int = Query(default=100, ge=1, le=1000)):
    """查看记忆:layer=core/episodic/long_term/all;long_term 可按 category 过滤"""
    redis = await get_redis()
    out: dict = {"object_id": object_id}
    if layer in ("core", "all"):
        out["core"] = [f.to_dict() for f in await store.get_core(redis, object_id)]
    if layer in ("episodic", "all"):
        eps = await store.get_episodic(redis, object_id, limit=limit)
        out["episodic"] = [e.to_dict() for e in eps]
    if layer in ("long_term", "all"):
        items = await store.get_all_long_term(redis, object_id)
        if category:
            items = [m for m in items if m.category.value == category]
        out["long_term"] = [m.to_dict() for m in items[:limit]]
    return out


@router.get("/memory/{object_id}/stats", dependencies=[Depends(verify_token)])
async def memory_stats(object_id: str):
    """记忆统计:各层数量 + long-term 遗忘数"""
    redis = await get_redis()
    allm = await store.get_all_long_term(redis, object_id, include_forgotten=True)
    forgotten = sum(1 for m in allm if m.forgotten)
    return {
        "object_id": object_id,
        "core": len(await store.get_core(redis, object_id)),
        "episodic": await store.count_episodic(redis, object_id),
        "long_term_active": len(allm) - forgotten,
        "long_term_forgotten": forgotten,
    }


@router.delete("/memory/{object_id}/{mid}", dependencies=[Depends(verify_token)])
async def manual_forget(object_id: str, mid: str):
    """手动遗忘单条(置 forgotten=True,可恢复)"""
    from memory.coordinator import get_memory_coordinator
    redis = await get_redis()
    coord = await get_memory_coordinator()
    if not await coord.manual_forget(object_id, mid):
        raise HTTPException(status_code=404, detail="memory not found")
    return {"forgotten": True}


@router.post("/memory/{object_id}/{mid}/restore", dependencies=[Depends(verify_token)])
async def restore(object_id: str, mid: str):
    """恢复已遗忘单条"""
    from memory.coordinator import get_memory_coordinator
    redis = await get_redis()
    coord = await get_memory_coordinator()
    if not await coord.restore(object_id, mid):
        raise HTTPException(status_code=404, detail="memory not found")
    return {"restored": True}


@router.post("/memory/{object_id}/{mid}/lock", dependencies=[Depends(verify_token)])
async def lock(object_id: str, mid: str, body: dict = Body(default={})):
    """锁定/解锁单条(防遗忘)。body: {"locked": bool}(默认 True)"""
    redis = await get_redis()
    locked = bool(body.get("locked", True))
    if not await store.set_locked(redis, object_id, mid, locked):
        raise HTTPException(status_code=404, detail="memory not found")
    return {"locked": locked}


@router.patch("/memory/{object_id}/{mid}", dependencies=[Depends(verify_token)])
async def edit_memory(object_id: str, mid: str, body: dict = Body(default={})):
    """编辑长期记忆条目(2026-07-06 手动修正)。body: {content?, category?, importance?}(至少其一)。
    category 须为 fact/preference/relationship/event/personality。返回更新后的条目。"""
    content = body.get("content")
    category = body.get("category")
    importance = body.get("importance")
    if content is None and category is None and importance is None:
        raise HTTPException(status_code=400, detail="至少传 content/category/importance 之一")
    cat = None
    if category is not None:
        from memory.models import Category
        try:
            cat = Category(category)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"category 须为 {[c.value for c in Category]}")
    redis = await get_redis()
    ok = await store.update_long_term(
        redis, object_id, mid, content=content, category=cat,
        importance=float(importance) if importance is not None else None)
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    updated = await store.get_long_term(redis, object_id, mid)
    return updated.to_dict() if updated else {"updated": True}


@router.post("/memory/{object_id}/forget", dependencies=[Depends(verify_token)])
async def batch_forget(object_id: str, body: dict = Body(default={})):
    """批量遗忘:body {"category"?, "keyword"?}。返回遗忘条数"""
    from memory.coordinator import get_memory_coordinator
    redis = await get_redis()
    coord = await get_memory_coordinator()
    n = await coord.batch_forget(object_id,
                                 category=body.get("category", ""),
                                 keyword=body.get("keyword", ""))
    return {"forgotten": n}
