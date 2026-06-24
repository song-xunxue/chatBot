"""
管理面板杂项 REST：模型 provider 列表 / 对话历史 / 人格进化提案审核。
对应 M7 面板的 Model / History / Roleplay 页面；Roleplay 页消费 M4.4 persona_evolve 提案，
闭合"人格反推→人工确认"环（提案不自动改写人设）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M7 创建 rest_admin：models / history / persona_evolve proposals
"""
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from core.config import settings
from storage.redis_client import get_redis
from storage import chat_store

router = APIRouter(prefix="/api/v1", tags=["admin"])


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖：Header 或 query 任一通过；显式拒绝空 token"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


@router.get("/models", dependencies=[Depends(_auth)])
async def list_models():
    """LLM provider 列表：是否已配置 key、是否可用"""
    from llm.registry import available_providers
    avail = available_providers()
    providers = []
    for name in ("glm", "deepseek", "siliconflow"):
        key = getattr(settings, f"{name}_api_key", "")
        providers.append({"name": name, "configured": bool(key), "available": name in avail})
    return {"providers": providers, "default": "glm"}


@router.get("/history/{object_id}", dependencies=[Depends(_auth)])
async def get_history(object_id: str, limit: int = Query(50, ge=1, le=500)):
    """按对象查看对话历史（chat_store Working 层）"""
    redis = await get_redis()
    msgs = await chat_store.get_history(redis, object_id, limit=limit)
    return {
        "object_id": object_id,
        "messages": [
            {"role": m.role, "content": m.content, "ts": getattr(m, "ts", 0)}
            for m in msgs
        ],
    }


@router.get("/persona_evolve/proposals", dependencies=[Depends(_auth)])
async def list_proposals():
    """列出所有待审核的人格进化提案（M4.4 persona_evolve 写入）"""
    redis = await get_redis()
    out = []
    async for key in redis.scan_iter(match="mychat:persona_evolve:proposal:*"):
        k = key.decode() if isinstance(key, bytes) else key
        oid = k.rsplit(":", 1)[-1]
        raw = await redis.get(k)
        try:
            data = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        out.append({"object_id": oid, "samples": data.get("samples", [])})
    return {"proposals": out}


@router.delete("/persona_evolve/proposals/{object_id}", dependencies=[Depends(_auth)])
async def dismiss_proposal(object_id: str):
    """忽略/驳回一条人格进化提案（删除提案键，不落库改人设）"""
    redis = await get_redis()
    n = await redis.delete(f"mychat:persona_evolve:proposal:{object_id}")
    return {"dismissed": n > 0}
