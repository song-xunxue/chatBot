"""
心情系统 REST 接口(M7):mood 值读写 + 档位 CRUD + 全局参数 + 历史曲线 + 评分试算。
对应 docs/03 §10。鉴权 X-Access-Token。

路由(prefix /api/v1):
  GET    /mood/kinds                  列全部档位
  POST   /mood/kinds                  新增/编辑档位(upsert,校验范围冲突,失败 400)
  PUT    /mood/kinds/{key}            编辑档位(同 upsert)
  DELETE /mood/kinds/{key}            删档位(校验覆盖,失败 400)
  GET    /mood/params                 取全局参数
  PUT    /mood/params                 改全局参数(校验 [0,1],失败 400)
  GET    /mood/{object_id}            取某对象当前 mood + 所在档位
  PUT    /mood/{object_id}            手动设置某对象 mood
  GET    /mood/{object_id}/history    mood 历史曲线(近 N 点,旧→新正序)
  POST   /mood/{object_id}/calc       评分试算(score_base + mood → mood_bias 均值 + score)

作者: 李文煜
日期: 2026-06-30
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from api._auth import verify_token
from storage.redis_client import get_redis
from mood import service as mood_service

router = APIRouter(prefix="/api/v1", tags=["mood"])

_CALC_SAMPLES = 20   # 试算采样次数(compute_mood_bias 含 random 噪声,多次采样取均值)


# —— 档位 CRUD ——

@router.get("/mood/kinds", dependencies=[Depends(verify_token)])
async def list_kinds():
    redis = await get_redis()
    return await mood_service.list_kinds(redis)


@router.post("/mood/kinds", dependencies=[Depends(verify_token)])
async def upsert_kind_route(body: dict):
    """新增/编辑档位(upsert,校验范围冲突)。失败返 400。"""
    redis = await get_redis()
    try:
        await mood_service.upsert_kind(redis, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await mood_service.get_kind(redis, body.get("key", ""))


@router.put("/mood/kinds/{key}", dependencies=[Depends(verify_token)])
async def put_kind(key: str, body: dict):
    """编辑档位(body 无 key 时用路径 key)"""
    body = {**body, "key": key}
    redis = await get_redis()
    try:
        await mood_service.upsert_kind(redis, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await mood_service.get_kind(redis, key)


@router.delete("/mood/kinds/{key}", dependencies=[Depends(verify_token)])
async def delete_kind_route(key: str):
    redis = await get_redis()
    try:
        await mood_service.delete_kind(redis, key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"deleted": True, "key": key}


# —— 全局参数 ——

@router.get("/mood/params", dependencies=[Depends(verify_token)])
async def get_params():
    redis = await get_redis()
    return await mood_service.get_params(redis)


@router.put("/mood/params", dependencies=[Depends(verify_token)])
async def put_params(body: dict):
    redis = await get_redis()
    try:
        return await mood_service.set_params(redis, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# —— 对象 mood + 历史 + 试算 ——

@router.get("/mood/{object_id}", dependencies=[Depends(verify_token)])
async def get_mood_route(object_id: str):
    """取某对象当前 mood 值 + 所在档位"""
    redis = await get_redis()
    mood = await mood_service.get_mood(redis, object_id)
    kinds = await mood_service.list_kinds(redis)
    return {"object_id": object_id, "mood": mood, "kind": mood_service.lookup_kind(mood, kinds)}


@router.put("/mood/{object_id}", dependencies=[Depends(verify_token)])
async def set_mood_route(object_id: str, body: dict):
    """手动设置 mood。body: {mood: float}"""
    if "mood" not in body:
        raise HTTPException(status_code=400, detail="mood required")
    try:
        mood = float(body["mood"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="mood must be float")
    redis = await get_redis()
    await mood_service.set_mood(redis, object_id, mood)
    return {"object_id": object_id, "mood": await mood_service.get_mood(redis, object_id)}


@router.get("/mood/{object_id}/history", dependencies=[Depends(verify_token)])
async def mood_history(object_id: str, limit: int = Query(default=100, ge=1, le=1000)):
    redis = await get_redis()
    return await mood_service.get_history_curve(redis, object_id, limit=limit)


@router.post("/mood/{object_id}/calc", dependencies=[Depends(verify_token)])
async def mood_calc(object_id: str, body: dict):
    """评分试算:给定 score_base + mood → mood_bias(多次采样均值避噪声)+ score。
    body: {score_base: int, mood?: float}(mood 缺省取对象当前值)"""
    if "score_base" not in body:
        raise HTTPException(status_code=400, detail="score_base required")
    try:
        score_base = int(body["score_base"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="score_base must be int")
    redis = await get_redis()
    raw_mood = body.get("mood")
    mood = await mood_service.get_mood(redis, object_id) if raw_mood is None else raw_mood
    try:
        mood = float(mood)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="mood must be float")
    kinds = await mood_service.list_kinds(redis)
    biases = [mood_service.compute_mood_bias(mood, kinds) for _ in range(_CALC_SAMPLES)]
    mood_bias = round(sum(biases) / len(biases), 2)
    score = max(0, min(100, round(score_base + mood_bias)))
    return {"score_base": score_base, "mood": mood, "mood_bias": mood_bias, "score": score}
