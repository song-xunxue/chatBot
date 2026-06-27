"""
评分系统 REST 接口(M3)
取分 / 手动改分 / 人设健康度 / 反推预览(dry_run)/ 反推落库(apply)。
鉴权沿用 X-Access-Token(Header 或 query 任一)。对应 docs/02 §12.2 / docs/01 §4。

路由(prefix /api/v1):
  GET   /chat/messages/{mid}/score              取 score 四元组
  PATCH /chat/messages/{mid}/score              手动改分(覆盖 score_base,重算 score)
  GET   /chat/{object_id}/health                人设健康度(近 N 条均分 + 正/负/中计数)
  POST  /score/reverse_infer/{object_id}/dry_run 反推预览(返回 diff + confirm_token)
  POST  /score/reverse_infer/{object_id}/apply   反推落库(凭 confirm_token)

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 新建 rest_score:GET/PATCH score、GET health、POST reverse_infer dry_run/apply
"""
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from core.config import settings
from storage.redis_client import get_redis

router = APIRouter(prefix="/api/v1", tags=["score"])


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖:Header 或 query 任一通过;显式拒绝空 token(与 V1.0 各 router 一致)"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


@router.get("/chat/messages/{mid}/score", dependencies=[Depends(_auth)])
async def get_score(mid: str):
    """取该消息 score 四元组(+ score_reason/score_manual 标记)"""
    from score import service as score_service
    redis = await get_redis()
    data = await score_service.get_score(redis, mid)
    if data is None:
        raise HTTPException(status_code=404, detail="message not found")
    return data


@router.patch("/chat/messages/{mid}/score", dependencies=[Depends(_auth)])
async def manual_set_score(mid: str, body: dict):
    """手动改分:覆盖 score_base,重算 score(保留历史 mood_bias)。body: {"score_base": int}"""
    from score import service as score_service
    if "score_base" not in body:
        raise HTTPException(status_code=400, detail="score_base required")
    try:
        score_base = int(body["score_base"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="score_base must be int")
    redis = await get_redis()
    data = await score_service.manual_set_score(redis, mid, score_base)
    if data is None:
        raise HTTPException(status_code=404, detail="message not found")
    return data


@router.get("/chat/{object_id}/health", dependencies=[Depends(_auth)])
async def persona_health(object_id: str, window: int = Query(default=0, ge=0)):
    """人设健康度:近 window 条 ai/proxy 消息 score 均分 + 正/负/中样本计数。
    window=0 时用默认 score_health_window。低均分预警人设跑偏。"""
    from score import service as score_service
    redis = await get_redis()
    return await score_service.persona_health(redis, object_id, window=window or None)


@router.post("/score/reverse_infer/{object_id}/dry_run", dependencies=[Depends(_auth)])
async def reverse_infer_dry_run(object_id: str, body: dict = Body(default={})):
    """反推预览:取评分正/负样本→LLM 提炼→构建 diff→返回 {diff, confirm_token, ...}。
    body 可选: {"mode": "fill_empty|overwrite", "provider": "..."}。
    预览不可绕过:apply 须凭本接口返回的 confirm_token。"""
    if not settings.reverse_infer_enabled:
        raise HTTPException(status_code=403, detail="reverse_infer disabled")
    from score.reverse_infer import infer_and_merge
    redis = await get_redis()
    return await infer_and_merge(
        redis, object_id, mode=body.get("mode"),
        dry_run=True, provider_name=body.get("provider", ""),
    )


@router.post("/score/reverse_infer/{object_id}/apply", dependencies=[Depends(_auth)])
async def reverse_infer_apply(object_id: str, body: dict):
    """反推落库:凭 confirm_token 取暂存 diff→snapshot→合并→set。body: {"confirm_token": "..."}"""
    if not settings.reverse_infer_enabled:
        raise HTTPException(status_code=403, detail="reverse_infer disabled")
    token = body.get("confirm_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="confirm_token required")
    from score.reverse_infer import infer_and_merge
    redis = await get_redis()
    return await infer_and_merge(redis, object_id, dry_run=False, confirm_token=token)
