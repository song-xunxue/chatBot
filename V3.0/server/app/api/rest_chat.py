"""
聊天历史 REST 接口(M7):block 三层浏览 + 消息软删(联动 neg)+ 关 block。
对应 docs/02 §12.1。鉴权 X-Access-Token(Header 或 query)。

路由(prefix /api/v1):
  GET    /chat/{object_id}/blocks        列会话所有 block(含 status/时间/summary/msg_count)
  GET    /chat/{object_id}/messages      列消息(block_id 可选,limit 截断;完整字段含 score 四元组)
  GET    /chat/messages/{mid}            按 mid 取单条
  DELETE /chat/messages/{mid}            物理删单条(ai/proxy + 有 score → 删前联动写 neg)
  POST   /chat/blocks/{block_id}/close   手动关闭 block(close_reason=manual)

作者: 李文煜
日期: 2026-06-30

2026-08-18
变更说明：
  1. 删 PUT /chat/messages/{mid}(编辑内容):破坏性改 content 与"纠正回复"功能语义重复
     (纠错走 PATCH score 的 corrected:原内容保留+正样本反推),用户裁决移除
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from api._auth import verify_token
from storage.redis_client import get_redis
from storage import chat_store

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.get("/chat/sessions", dependencies=[Depends(verify_token)])
async def list_sessions(limit: int = Query(default=50, ge=1, le=500)):
    """列最近活跃会话(跨所有 object_id,按最近活跃倒序),供面板历史页自动展示(无需手输 object_id)。
    返回 [{object_id, last_ts, block_count}]。"""
    redis = await get_redis()
    return await chat_store.list_recent_sessions(redis, limit=limit)


@router.get("/chat/recent_blocks", dependencies=[Depends(verify_token)])
async def list_recent_blocks(limit: int = Query(default=50, ge=1, le=500)):
    """列最近活跃 block(跨所有 object_id,按 start_ts 倒序),供面板历史页 block 级会话列表。
    单用户场景:每个 block = 一段会话。返回 [{block_id, object_id, start_ts, end_ts, status, msg_count}]。"""
    redis = await get_redis()
    return await chat_store.list_recent_blocks(redis, limit=limit)


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


@router.delete("/chat/messages/{mid}", dependencies=[Depends(verify_token)])
async def delete_message(mid: str):
    """物理删单条消息(2026-08-18 真删除:msg Hash + block msgs 索引移除,会话不再出现)。
    原软删只打 status=deleted 标记、内容永留——对齐 QQ 客户端删除语义。
    删前联动:sender∈(ai,proxy) 且有 score → 写 score neg 队列(文本副本进样本,训练价值不丢)。"""
    redis = await get_redis()
    msg = await chat_store.get_message(redis, mid)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    # 删前联动 neg(ai/proxy 且有 score;软失败不阻塞删除)
    # 审查修复(2026-09-07):先 remove_sample_by_mid 清 pos/neg 队列同 mid 旧样本再写 neg——
    # 否则删除恒正样本(手动回复[手]100/纠正[纠]100)后 pos 残留,同一文本同时以
    # 黄金正样本+负样本驱动反推,互相矛盾
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
                oid = msg.get("object_id", "")
                if oid:
                    await score_service.remove_sample_by_mid(redis, oid, mid)
                await score_service.record_negative_sample(
                    redis, oid, mid, msg.get("content", ""), score)
                linked = True
    ok = await chat_store.hard_delete_message(redis, mid)
    return {"deleted": ok, "neg_linked": linked}


@router.post("/chat/blocks/{block_id}/close", dependencies=[Depends(verify_token)])
async def close_block(block_id: str, body: dict = Body(default={})):
    """手动关闭 block(close_reason=manual)。body: {reason?}"""
    redis = await get_redis()
    await chat_store.close_block(redis, block_id, reason=body.get("reason", "manual"))
    return {"closed": True, "block_id": block_id}


@router.delete("/chat/blocks/{block_id}", dependencies=[Depends(verify_token)])
async def delete_block(block_id: str):
    """物理删单个 block + 其全部消息(2026-07-05 会话整体删除)。
    删前联动:ai/proxy 有 score 的消息写 score neg 队列保留反推样本。返回 {deleted_msgs, neg_linked}。"""
    redis = await get_redis()
    r = await chat_store.delete_block(redis, block_id)
    return {"deleted": True, **r}


@router.delete("/chat/{object_id}/history", dependencies=[Depends(verify_token)])
async def delete_object_history(object_id: str):
    """清空该 object_id 全部历史(所有 block + 消息,2026-07-05 清空全部)。
    逐 block 联动 neg。返回 {deleted_blocks, deleted_msgs, neg_linked}。"""
    redis = await get_redis()
    return {"deleted": True, **await chat_store.delete_object_history(redis, object_id)}
