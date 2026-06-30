"""
代人聊天代答 REST 接口(M8):开关/状态/列队列/单条+批量代答/跳过。
对应 docs/02 §12.4。鉴权 verify_token(Header 或 query)。代答产出全链路在 takeover/service。

路由(prefix /api/v1):
  POST /takeover/{oid}/toggle          开关代答模式
  GET  /takeover/{oid}/status          开关状态 + 队列长度
  GET  /takeover/{oid}/queue           列 pending 队列(带孤儿过滤)
  POST /takeover/{oid}/answer          单条代答(pid 空取队首)
  POST /takeover/{oid}/answer/batch    批量代答(逐条下发 QQ)
  POST /takeover/{oid}/skip            跳过(队首或指定 pid)

作者: 李文煜
日期: 2026-06-30
"""
from fastapi import APIRouter, Body, Depends, HTTPException

from api._auth import verify_token
from storage.redis_client import get_redis
from storage import takeover_store
from takeover import service as takeover_svc

router = APIRouter(prefix="/api/v1", tags=["takeover"])


@router.post("/takeover/{oid}/toggle", dependencies=[Depends(verify_token)])
async def toggle(oid: str, body: dict = Body(default={})):
    """开关代答模式。body: {enabled: bool}"""
    enabled = bool(body.get("enabled"))
    redis = await get_redis()
    await takeover_store.set_enabled(redis, oid, enabled)
    return {"object_id": oid, "enabled": enabled}


@router.get("/takeover/{oid}/status", dependencies=[Depends(verify_token)])
async def status(oid: str):
    """代答开关状态 + 队列长度"""
    redis = await get_redis()
    return {
        "object_id": oid,
        "enabled": await takeover_store.is_enabled(redis, oid),
        "queue_length": await takeover_store.queue_length(redis, oid),
    }


@router.get("/takeover/{oid}/queue", dependencies=[Depends(verify_token)])
async def queue(oid: str):
    """列 pending 队列(FIFO 正序,带孤儿过滤)"""
    redis = await get_redis()
    return {"object_id": oid, "queue": await takeover_store.list_queue(redis, oid)}


@router.post("/takeover/{oid}/answer", dependencies=[Depends(verify_token)])
async def answer(oid: str, body: dict = Body(default={})):
    """单条代答。body: {pid?, answer}。pid 空取队首。代答产出全链路(落 proxy+评分+记忆+心情+下发)。
    pending 不存在/过期 → 404。"""
    pid = body.get("pid") or None
    ans = (body.get("answer") or "").strip()
    if not ans:
        raise HTTPException(status_code=400, detail="answer required")
    redis = await get_redis()
    try:
        return await takeover_svc.resolve_and_deliver(redis, oid, pid, ans)
    except takeover_svc.TakeoverNotFound:
        raise HTTPException(status_code=404, detail="pending not found or expired")


@router.post("/takeover/{oid}/answer/batch", dependencies=[Depends(verify_token)])
async def answer_batch(oid: str, body: dict = Body(default={})):
    """批量代答。body: {items: [{pid?, answer}]}。逐条下发 QQ,受 takeover_batch_max 截断。
    返回 {results, success, truncated}。"""
    items = body.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="items required")
    redis = await get_redis()
    return await takeover_svc.resolve_and_deliver_batch(redis, oid, items)


@router.post("/takeover/{oid}/skip", dependencies=[Depends(verify_token)])
async def skip(oid: str, body: dict = Body(default={})):
    """跳过(放弃代答)。body: {pid?}。pid 空跳队首。命中返 True。"""
    pid = body.get("pid") or None
    redis = await get_redis()
    hit = await takeover_store.skip(redis, oid, pid)
    return {"skipped": hit, "pid": pid}
