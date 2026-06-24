"""
代人聊天 A：面板模拟训练 REST（V1.1 M11）
录/列/改/删 roleplay 正样本对话（物理隔离，用作反推正样本来源）。
对应 docs/10 §6。反推合并由 M12 reverse_infer 负责，本模块只产数据。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. V1.1 M11 创建 roleplay-training 端点组（messages CRUD + object_id 绑定校验）
"""
from fastapi import APIRouter, HTTPException, Header, Query, Depends

from storage.redis_client import get_redis
from storage import chat_store
from persona import store as persona_store
from core.config import settings

router = APIRouter(prefix="/api/v1/roleplay", tags=["roleplay"])

# persona_store 的对象绑定键（与 store._K_BIND 一致，此处单独列避免私有访问）
_K_BIND = "mychat:obj:{oid}:persona"


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖：Header 或 query 任一通过即可；显式拒绝空 token"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


async def _check_bound(redis, object_id: str) -> str:
    """校验 object_id 已绑定人设才允许录入（防孤儿 chat List）。返回绑定的 persona_id。"""
    bound = await redis.get(_K_BIND.format(oid=object_id))
    if not bound:
        raise HTTPException(status_code=400, detail=f"对象 {object_id} 未绑定人设，请先在面板绑定")
    return await persona_store.get_object_persona_id(redis, object_id)


@router.post("/{object_id}/messages", dependencies=[Depends(_auth)])
async def add_message(object_id: str, body: dict):
    """录一对 roleplay 对话（user 说什么 + 角色该回什么）"""
    user_text = (body.get("user_text") or "").strip()
    assistant_text = (body.get("assistant_text") or "").strip()
    if not user_text or not assistant_text:
        raise HTTPException(status_code=400, detail="user_text 和 assistant_text 均必填")
    redis = await get_redis()
    await _check_bound(redis, object_id)
    mid_u, mid_a, ts = await chat_store.append_roleplay_pair(redis, object_id, user_text, assistant_text)
    return {"mid_user": mid_u, "mid_assistant": mid_a, "ts": ts}


@router.get("/{object_id}/messages", dependencies=[Depends(_auth)])
async def list_messages(object_id: str, limit: int = Query(1000, ge=1, le=1000)):
    """列出该对象的 roleplay 正样本（带 mid，正序）"""
    redis = await get_redis()
    msgs = await chat_store.list_roleplay(redis, object_id, limit=limit)
    return {"object_id": object_id, "messages": msgs}


@router.put("/{object_id}/messages/{mid}", dependencies=[Depends(_auth)])
async def update_message(object_id: str, mid: str, body: dict):
    """改写单条 roleplay 对话内容（自主编辑改善样本）"""
    content = body.get("content")
    if content is None:
        raise HTTPException(status_code=400, detail="content 必填")
    redis = await get_redis()
    hit = await chat_store.update_roleplay(redis, object_id, mid, content)
    if not hit:
        raise HTTPException(status_code=404, detail="message not found")
    return {"updated": True}


@router.delete("/{object_id}/messages/{mid}", dependencies=[Depends(_auth)])
async def delete_message(object_id: str, mid: str):
    """删除单条 roleplay 对话（删=负样本信号，同步写入 neg 队列）"""
    redis = await get_redis()
    hit = await chat_store.delete_roleplay(redis, object_id, mid)
    if not hit:
        raise HTTPException(status_code=404, detail="message not found")
    return {"deleted": True}


# —— V1.1 M12：反推人设·直接合并（两步契约：infer 预览 → apply 落库）——

@router.post("/{object_id}/reverse-infer", dependencies=[Depends(_auth)])
async def reverse_infer(object_id: str, body: dict):
    """触发反推（强制 dry_run 预览，不可绕过）。返回 diff + confirm_token。
    body: {mode?: 'fill_empty'|'overwrite'}（默认 fill_empty 只填空字段）。"""
    from persona import reverse_infer as ri
    mode = body.get("mode", "fill_empty")
    redis = await get_redis()
    return await ri.infer_and_merge(redis, object_id, mode=mode, dry_run=True)


@router.post("/{object_id}/reverse-infer/apply", dependencies=[Depends(_auth)])
async def reverse_infer_apply(object_id: str, body: dict):
    """凭 confirm_token 落库合并（合并前自动快照入 history，支持回滚）。"""
    from persona import reverse_infer as ri
    token = body.get("confirm_token", "")
    redis = await get_redis()
    return await ri.infer_and_merge(redis, object_id, dry_run=False, confirm_token=token)
