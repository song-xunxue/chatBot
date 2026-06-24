"""
代人聊天 B 回推 REST（V1.1 M13）
面板代答经 REST 提交，服务端校验 pending 后广播 ai_done 到客户端 + takeover_resolved 到面板，
代答入库（source=takeover）+ 采集正样本（D6 代答进四级记忆）。
对应 docs/10 §8。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. V1.1 M13 创建 rest_takeover：toggle/status/pending/answer
"""
from fastapi import APIRouter, HTTPException, Header, Query, Depends

from shared.protocol import (  # shared 在项目根，ws.py 已把根加入 sys.path；此处运行时可见
    envelope, now_ts, TYPE_AI_DONE, TYPE_TAKEOVER_RESOLVED,
)
from storage.redis_client import get_redis
from storage import chat_store
from plugins.connections import get_connection_registry
from core.config import settings
from takeover import service as takeover_svc, panel_bus

router = APIRouter(prefix="/api/v1/takeover", tags=["takeover"])


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖：Header 或 query 任一通过即可；显式拒绝空 token"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


@router.post("/toggle", dependencies=[Depends(_auth)])
async def toggle(body: dict):
    """开启/关闭某对象的代人模式"""
    oid = body.get("object_id", "")
    enabled = bool(body.get("enabled"))
    if not oid:
        raise HTTPException(status_code=400, detail="object_id required")
    redis = await get_redis()
    await takeover_svc.set_takeover_enabled(redis, oid, enabled)
    return {"object_id": oid, "enabled": enabled}


@router.get("/status", dependencies=[Depends(_auth)])
async def status(object_id: str = Query(...)):
    """某对象代人开关状态 + 当前 active pending"""
    redis = await get_redis()
    return {
        "object_id": object_id,
        "enabled": await takeover_svc.is_takeover_enabled(redis, object_id),
        "active_pending": await takeover_svc.get_active_pending(redis, object_id),
    }


@router.get("/pending", dependencies=[Depends(_auth)])
async def pending():
    """列出所有未决代答请求（面板待答列表）"""
    redis = await get_redis()
    return {"requests": await takeover_svc.list_pending(redis)}


@router.post("/answer", dependencies=[Depends(_auth)])
async def answer(body: dict):
    """面板代答提交：校验 pending → 广播 ai_done 到客户端 → resolved 到面板 → 入库 → D6 进记忆"""
    oid = body.get("object_id", "")
    pending_id = body.get("pending_id", "")
    ans = (body.get("answer") or "").strip()
    if not oid or not pending_id or not ans:
        raise HTTPException(status_code=400, detail="object_id/pending_id/answer required")
    redis = await get_redis()
    resolved = await takeover_svc.resolve_takeover_answer(redis, oid, pending_id, ans)
    if not resolved:
        raise HTTPException(status_code=410, detail="pending expired or invalid")
    # 广播 ai_done 到客户端（source=takeover）
    sent = await get_connection_registry().broadcast(oid, envelope(
        TYPE_AI_DONE, {"text": ans, "source": "takeover"}, object_id=oid, ts=now_ts()))
    # 通知面板该请求已处理
    await panel_bus.broadcast_to_panels(envelope(
        TYPE_TAKEOVER_RESOLVED, {"pending_id": pending_id, "object_id": oid}, ts=now_ts()))
    # 入库 assistant（source=takeover，作为反推正样本数据源）
    await chat_store.append_message(redis, oid, "assistant", ans, source="takeover")
    # D6：代答进四级记忆（触发协调器编码 Episodic/Long-term，失败不崩）
    if settings.memory_enabled:
        try:
            from memory.coordinator import get_memory_coordinator
            coord = await get_memory_coordinator()
            await coord.on_turn_complete(oid, resolved["user_text"], ans)
        except Exception:
            pass
    await takeover_svc.clear_pending(redis, oid, pending_id)
    return {"resolved": True, "sent": sent}
