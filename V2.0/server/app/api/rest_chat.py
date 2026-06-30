"""
聊天历史 REST 接口(M7):block 三层浏览 + 消息编辑/软删(联动 neg)+ 关 block。
对应 docs/02 §12.1。鉴权 X-Access-Token(Header 或 query)。

路由(prefix /api/v1):
  GET    /chat/{object_id}/blocks        列会话所有 block(含 status/时间/summary/msg_count)
  GET    /chat/{object_id}/messages      列消息(block_id 可选,limit 截断;完整字段含 score 四元组)
  GET    /chat/messages/{mid}            按 mid 取单条
  PUT    /chat/messages/{mid}            编辑(→ status=edited)
  DELETE /chat/messages/{mid}            软删(→ status=deleted;ai/proxy + 有 score → 联动写 neg)
  POST   /chat/blocks/{block_id}/close   手动关闭 block(close_reason=manual)

作者: 李文煜
日期: 2026-06-30
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from api._auth import verify_token
from storage.redis_client import get_redis
from storage import chat_store

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.get("/chat/{object_id}/blocks", dependencies=[Depends(verify_token)])
async def list_blocks(object_id: str, limit: int = Query(default=100, ge=1, le=1000)):
    """列出会话所有 block(按 start_ts 倒序,最近在前),含 status/时间/summary/msg_count"""
    redis = await get_redis()
    return await chat_store.list_blocks(redis, object_id, limit=limit)


@router.get("/chat/{object_id}/messages", dependencies=[Depends(verify_token)])
async def list_messages(object_id: str,
                        block_id: str = Query(default=""),
                        limit: int = Query(default=500, ge=1, le=5000)):
    """列消息(完整字段含 score 四元组)。block_id 指定则只列该 block;否则跨 block 取最近 limit 条。"""
    redis = await get_redis()
    return await chat_store.list_messages(redis, object_id, block_id=block_id or None, limit=limit)


@router.get("/chat/messages/{mid}", dependencies=[Depends(verify_token)])
async def get_message(mid: str):
    """按 mid 取单条消息(含 score 四元组)"""
    redis = await get_redis()
    msg = await chat_store.get_message(redis, mid)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    return msg


@router.put("/chat/messages/{mid}", dependencies=[Depends(verify_token)])
async def update_message(mid: str, body: dict = Body(default={})):
    """编辑消息内容/sender(→ status=edited)。body: {content?, sender?}"""
    redis = await get_redis()
    ok = await chat_store.update_message(redis, mid,
                                         content=body.get("content"),
                                         sender=body.get("sender"))
    if not ok:
        raise HTTPException(status_code=404, detail="message not found")
    return await chat_store.get_message(redis, mid)


@router.delete("/chat/messages/{mid}", dependencies=[Depends(verify_token)])
async def delete_message(mid: str, body: dict = Body(default={})):
    """软删消息(→ status=deleted,保留供反推)。body: {reason?}。
    联动(docs/02 §12.1):若 sender∈(ai,proxy) 且消息有 score,同步写 score neg 队列扩充反推负样本。"""
    redis = await get_redis()
    msg = await chat_store.get_message(redis, mid)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    await chat_store.delete_message(redis, mid, reason=body.get("reason", "out_of_character"))
    # 软删联动:ai/proxy 且有 score → 写 neg 队列
    linked = False
    if msg.get("sender") in ("ai", "proxy"):
        raw_score = msg.get("score", "")
        if raw_score not in ("", None):
            try:
                score = int(float(raw_score))
            except (TypeError, ValueError):
                score = None
            if score is not None:
                from score import service as score_service
                await score_service.record_negative_sample(
                    redis, msg.get("object_id", ""), mid, msg.get("content", ""), score)
                linked = True
    return {"deleted": True, "status": "deleted", "neg_linked": linked}


@router.post("/chat/blocks/{block_id}/close", dependencies=[Depends(verify_token)])
async def close_block(block_id: str, body: dict = Body(default={})):
    """手动关闭 block(close_reason=manual)。body: {reason?}"""
    redis = await get_redis()
    await chat_store.close_block(redis, block_id, reason=body.get("reason", "manual"))
    return {"closed": True, "block_id": block_id}
