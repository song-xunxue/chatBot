"""
记忆 REST 接口
查看 / 手动遗忘 / 恢复 / 锁定 / 批量遗忘 / 导入学习 / 统计。
复用 ws.py 同款 access_token 鉴权。对应 docs/09 §6.2。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.5 创建记忆 REST 接口
  2. 修正路由顺序：字面量子路径（stats）注册在动态 {mid} 路由之前，避免被 {mid} 吞掉
"""
from fastapi import APIRouter, HTTPException, Header, Query, Depends

from storage.redis_client import get_redis
from memory import store, encoder
from memory.coordinator import get_memory_coordinator
from core.config import settings

router = APIRouter(prefix="/api/v1", tags=["memory"])


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖：Header 或 query 任一通过即可；显式拒绝空 token（防误配开放）"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


@router.get("/memory/{object_id}", dependencies=[Depends(_auth)])
async def get_memory(object_id: str, layer: str = "all",
                     category: str = "", page: int = 1, size: int = 50):
    """查看记忆，可按 layer(core/episodic/long_term/all) 与 category 过滤"""
    redis = await get_redis()
    result: dict = {}
    if layer in ("all", "core"):
        result["core"] = [f.to_dict() for f in await store.get_core(redis, object_id)]
    if layer in ("all", "episodic"):
        result["episodic"] = [e.to_dict() for e in await store.get_episodic(redis, object_id, limit=size)]
    if layer in ("all", "long_term"):
        items = await store.get_all_long_term(redis, object_id, include_forgotten=False)
        if category:
            items = [m for m in items if m.category.value == category]
        result["long_term"] = [m.to_dict() for m in items]
    return result


# 字面量子路径须注册在动态 {mid} 路由之前，否则 /memory/{oid}/stats 会被 {mid} 吞掉
@router.get("/memory/{object_id}/stats", dependencies=[Depends(_auth)])
async def stats(object_id: str):
    """记忆统计：各层数量、遗忘数"""
    redis = await get_redis()
    allm = await store.get_all_long_term(redis, object_id, include_forgotten=True)
    active = [m for m in allm if not m.forgotten]
    return {
        "long_term_total": len(allm),
        "long_term_active": len(active),
        "long_term_forgotten": len(allm) - len(active),
        "episodic_count": await store.count_episodic(redis, object_id),
    }


@router.post("/memory/{object_id}/forget", dependencies=[Depends(_auth)])
async def batch_forget(object_id: str, body: dict = None):
    """批量遗忘，body: {category?, keyword?}"""
    coord = await get_memory_coordinator()
    body = body or {}
    n = await coord.batch_forget(object_id,
                                 category=body.get("category", ""),
                                 keyword=body.get("keyword", ""))
    return {"forgotten_count": n}


@router.post("/memory/{object_id}/import", dependencies=[Depends(_auth)])
async def import_learn(object_id: str, body: dict):
    """导入聊天记录学习（F-C-05 正样本）：对 user 消息触发事实抽取写入长期记忆。
    body: {messages: [{role, content}, ...]}"""
    coord = await get_memory_coordinator()
    messages = (body or {}).get("messages", [])
    user_texts = [m.get("content", "") for m in messages
                  if isinstance(m, dict) and m.get("role") == "user"]
    if not user_texts or not coord.llm:
        return {"imported_facts": 0}
    facts = await encoder.extract_facts("\n".join(user_texts), "", coord.llm, coord._summary_model())
    for f in facts:
        await coord._upsert_fact_dedup(object_id, f)
    return {"imported_facts": len(facts)}


@router.get("/memory/{object_id}/{mid}", dependencies=[Depends(_auth)])
async def get_one(object_id: str, mid: str):
    """查看单条长期记忆"""
    redis = await get_redis()
    m = await store.get_long_term(redis, object_id, mid)
    if not m:
        raise HTTPException(status_code=404, detail="memory not found")
    return m.to_dict()


@router.delete("/memory/{object_id}/{mid}", dependencies=[Depends(_auth)])
async def forget_one(object_id: str, mid: str):
    """手动遗忘单条（置 forgotten=True）"""
    coord = await get_memory_coordinator()
    ok = await coord.manual_forget(object_id, mid)
    return {"forgotten": ok}


@router.post("/memory/{object_id}/lock/{mid}", dependencies=[Depends(_auth)])
async def lock_one(object_id: str, mid: str):
    """锁定防遗忘（locked=True）"""
    redis = await get_redis()
    if not await store.set_locked(redis, object_id, mid, True):
        raise HTTPException(status_code=404, detail="memory not found")
    return {"locked": True}


@router.post("/memory/{object_id}/restore/{mid}", dependencies=[Depends(_auth)])
async def restore_one(object_id: str, mid: str):
    """恢复已遗忘的单条"""
    coord = await get_memory_coordinator()
    ok = await coord.restore(object_id, mid)
    return {"restored": ok}
