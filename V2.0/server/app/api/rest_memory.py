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
    """编辑长期记忆条目。body 任一: {content?, category?, importance?, reason?, tags?,
    useful_score?, tier?, locked?}(至少其一,2026-08-13 扩 reason/tags/useful_score/tier)。
    category 须为 fact/preference/relationship/event/personality;
    tier 须为 -1(自动)/0/1/2;useful_score 须为 0-1。返回更新后的条目。"""
    content = body.get("content")
    category = body.get("category")
    importance = body.get("importance")
    reason = body.get("reason")
    tags = body.get("tags")
    useful_score = body.get("useful_score")
    tier = body.get("tier")
    if all(v is None for v in [content, category, importance, reason, tags, useful_score, tier]):
        raise HTTPException(status_code=400, detail="至少传一个可编辑字段")
    cat = None
    if category is not None:
        from memory.models import Category
        try:
            cat = Category(category)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"category 须为 {[c.value for c in Category]}")
    tier_v = None
    if tier is not None:
        try:
            tier_v = int(tier)
        except (TypeError, ValueError):
            tier_v = None
        if tier_v not in (-1, 0, 1, 2):
            raise HTTPException(status_code=400, detail="tier 须为 -1/0/1/2")
    us_v = None
    if useful_score is not None:
        try:
            us_v = float(useful_score)
        except (TypeError, ValueError):
            us_v = None
        if us_v is None or not (0.0 <= us_v <= 1.0):
            raise HTTPException(status_code=400, detail="useful_score 须为 0-1")
    tags_v = None
    if tags is not None:
        if not isinstance(tags, list):
            raise HTTPException(status_code=400, detail="tags 须为数组")
        tags_v = [str(t).strip() for t in tags if str(t).strip()][:5]
    redis = await get_redis()
    ok = await store.update_long_term(
        redis, object_id, mid,
        content=content, category=cat,
        importance=float(importance) if importance is not None else None,
        reason=str(reason) if reason is not None else None,
        tags=tags_v,
        useful_score=us_v,
        tier=tier_v,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    updated = await store.get_long_term(redis, object_id, mid)
    return updated.to_dict() if updated else {"updated": True}


@router.post("/memory/{object_id}", dependencies=[Depends(verify_token)])
async def create_memory(object_id: str, body: dict = Body(default={})):
    """手动新增长期记忆(2026-08-13 由用户完善角色记忆)。
    body: {content(必填), category?, importance?, reason?, tags?, useful_score?, tier?, locked?}。
    source 标记 'manual' 便于区分。返回新建条目。"""
    import uuid
    from memory.models import MemoryItem, Category
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content 必填")
    try:
        cat = Category(body.get("category", "fact"))
    except ValueError:
        raise HTTPException(status_code=400,
                            detail=f"category 须为 {[c.value for c in Category]}")
    importance = float(body.get("importance", 0.5))
    if not (0.0 <= importance <= 1.0):
        raise HTTPException(status_code=400, detail="importance 须为 0-1")
    useful_score = float(body.get("useful_score", importance))   # 默认同 importance
    if not (0.0 <= useful_score <= 1.0):
        raise HTTPException(status_code=400, detail="useful_score 须为 0-1")
    tier = int(body.get("tier", -1))
    if tier not in (-1, 0, 1, 2):
        raise HTTPException(status_code=400, detail="tier 须为 -1/0/1/2")
    tags = body.get("tags") or []
    if not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="tags 须为数组")
    tags = [str(t).strip() for t in tags if str(t).strip()][:5]
    redis = await get_redis()
    item = MemoryItem(
        id=f"mem_{uuid.uuid4().hex[:12]}",
        content=content,
        category=cat,
        importance=importance,
        reason=str(body.get("reason", "")).strip(),
        tags=tags,
        useful_score=useful_score,
        tier=tier,
        source="manual",
        locked=bool(body.get("locked", False)),
    )
    await store.upsert_long_term(redis, object_id, item)
    return item.to_dict()


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
