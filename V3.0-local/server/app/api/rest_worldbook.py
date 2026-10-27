"""
世界书 REST 接口(docs/09 §5,2026-10-26)
条目 CRUD(新建手写设定 source=manual)/ 统计 / 重建自动条目。
鉴权 X-Access-Token(Header 或 query),与 rest_memory 同款。面板 Worldbook.vue 消费。

路由(prefix /api/v1):
  GET    /worldbook/entries?source=&enabled=&limit=   条目列表(带 stats 字段)
  POST   /worldbook/entries                            新建手写设定条目
  PUT    /worldbook/entries/{eid}                      编辑条目(部分字段)
  DELETE /worldbook/entries/{eid}                      物理删除单条
  GET    /worldbook/stats                              顶部统计(总数/常驻/今日注入/平均 token)
  POST   /worldbook/rebuild                            从记忆体系全量重建自动条目(manual 保留)

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:entries CRUD + stats + rebuild 6 端点(全 verify_token)
  2. 审查修复:①数值字段坏类型裸 int()/float() 会 500,改 400;enabled 传字符串
     ("false" 被 bool() 求值为 True 语义反转)强制须为 JSON boolean;②source/source_ref
     移出 _EDITABLE——改成脏值会破坏 by_ref 幂等索引产生重复条目,改成自动来源还会被
     rebuild 物理删,面板本就以只读方式展示来源
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from storage.redis_client import get_redis
from api._auth import verify_token
from memory import worldbook, worldbook_store
from memory.worldbook import WbEntry

router = APIRouter(prefix="/api/v1", tags=["worldbook"])

# 可编辑字段白名单(PUT;mode/position 须合法值)。source/source_ref 不在列(见头部变更说明②)
_EDITABLE = ("title", "content", "key_regex", "mode", "position",
             "order", "probability", "cooldown_minutes", "keys", "secondary_keys", "enabled")


def _int_or_400(body: dict, key: str, default: int) -> int:
    """整数字段解析:缺省用 default;类型非法 → 400(替代裸 int() 的 ValueError 500)"""
    raw = body.get(key, default)
    if raw is None:
        raw = default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key} 须为整数")


def _float_or_400(body: dict, key: str, default: float) -> float:
    """浮点字段解析:缺省用 default;类型非法 → 400"""
    raw = body.get(key, default)
    if raw is None:
        raw = default
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key} 须为数字")


@router.get("/worldbook/entries", dependencies=[Depends(verify_token)])
async def list_entries(source: str = Query(default=""),
                       enabled: bool | None = Query(default=None),
                       limit: int = Query(default=0, ge=0)):
    """条目列表(created 倒序)。source 过滤(manual/memory/summary/diary/dream/roleplay)、
    enabled 过滤(true/false/空=全部)、limit>0 截断"""
    if source and source not in worldbook.SOURCES:
        raise HTTPException(status_code=400, detail=f"source 须为 {list(worldbook.SOURCES)}")
    redis = await get_redis()
    items = await worldbook_store.list_entries(redis, source=source, enabled=enabled, limit=limit)
    return {"items": [e.to_dict() for e in items]}


@router.post("/worldbook/entries", dependencies=[Depends(verify_token)])
async def create_entry(body: dict = Body(default={})):
    """新建手写设定条目(source=manual)。body: {title, content(必填), keys?, key_regex?,
    secondary_keys?, mode?, order?, position?, probability?, cooldown_minutes?}"""
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content 必填")
    entry = WbEntry(
        id=worldbook.new_entry_id(),
        title=(body.get("title") or content[:16]).strip(),
        content=content,
        keys=_keys(body.get("keys")),
        key_regex=str(body.get("key_regex", "") or ""),
        secondary_keys=_keys(body.get("secondary_keys")),
        mode=_mode(body.get("mode", "trigger")),
        order=_int_or_400(body, "order", 100),
        position=_position(body.get("position", "before_memories")),
        probability=max(0.0, min(1.0, _float_or_400(body, "probability", 1.0))),
        cooldown_minutes=max(0, _int_or_400(body, "cooldown_minutes", 0)),
        source="manual",
        source_ref="",
    )
    redis = await get_redis()
    return (await worldbook_store.upsert_entry(redis, entry)).to_dict()


@router.put("/worldbook/entries/{eid}", dependencies=[Depends(verify_token)])
async def update_entry(eid: str, body: dict = Body(default={})):
    """编辑条目(部分字段;至少其一)。mode/position 须合法;probability 0-1。返回更新后条目"""
    if not any(k in body for k in _EDITABLE):
        raise HTTPException(status_code=400, detail=f"至少传一个可编辑字段 {list(_EDITABLE)}")
    if "mode" in body and body["mode"] is not None and body["mode"] not in worldbook.MODES:
        raise HTTPException(status_code=400, detail=f"mode 须为 {list(worldbook.MODES)}")
    if ("position" in body and body["position"] is not None
            and body["position"] not in worldbook.POSITIONS):
        raise HTTPException(status_code=400,
                            detail=f"position 须为 {list(worldbook.POSITIONS)}")
    if "probability" in body and body["probability"] is not None:
        try:
            p = float(body["probability"])
        except (TypeError, ValueError):
            p = -1.0
        if not (0.0 <= p <= 1.0):
            raise HTTPException(status_code=400, detail="probability 须为 0-1")
    # 数值字段类型预校验(审查修复:store 层裸 int() 遇 "abc" 会 500);enabled 强制
    # JSON boolean——str "false" 在 store 层被 bool() 求值为 True,语义正好反转
    if "order" in body and body["order"] is not None:
        _int_or_400(body, "order", 100)
    if "cooldown_minutes" in body and body["cooldown_minutes"] is not None:
        _int_or_400(body, "cooldown_minutes", 0)
    if "enabled" in body and body["enabled"] is not None and not isinstance(body["enabled"], bool):
        raise HTTPException(status_code=400, detail="enabled 须为布尔(不是字符串)")
    redis = await get_redis()
    patch = {k: v for k, v in body.items() if k in _EDITABLE}
    entry = await worldbook_store.update_entry(redis, eid, patch)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry.to_dict()


@router.delete("/worldbook/entries/{eid}", dependencies=[Depends(verify_token)])
async def delete_entry(eid: str):
    """物理删除单条(自动条目的「遗忘」是 enabled=false,不走这)"""
    redis = await get_redis()
    if not await worldbook_store.delete_entry(redis, eid):
        raise HTTPException(status_code=404, detail="entry not found")
    return {"deleted": True}


@router.get("/worldbook/stats", dependencies=[Depends(verify_token)])
async def stats():
    """顶部统计(docs/09 §5):条目总数/启用数/常驻数/今日注入次数/平均注入 token/按来源分布"""
    redis = await get_redis()
    return await worldbook_store.get_stats(redis)


@router.post("/worldbook/rebuild", dependencies=[Depends(verify_token)])
async def rebuild(body: dict = Body(default={})):
    """重建自动条目:先删全部自动来源(memory/summary/diary/dream/roleplay)再按当前
    记忆体系全量重建(manual 条目不受影响;幂等,重复执行结果一致)。
    body {object_id?}:缺省扫全部对象(memory store.list_objects)"""
    from memory import store as mem_store
    redis = await get_redis()
    oid = str(body.get("object_id", "") or "").strip()
    oids = [oid] if oid else await mem_store.list_objects(redis)
    result = await worldbook_store.rebuild_auto(redis, oids)
    return result


def _keys(v) -> list[str]:
    """keys/secondary_keys 容错:list 转 str 去空白;非 list 兜底空"""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def _mode(v) -> str:
    return v if v in worldbook.MODES else "trigger"


def _position(v) -> str:
    return v if v in worldbook.POSITIONS else "before_memories"
