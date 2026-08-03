"""
roleplay 训练样本 REST 接口(M8 + 2026-07-05 多会话+评分):会话 CRUD + 录/批量录/列/改/删(→neg)
+ assistant 回复评分(联动反推样本队列)。对应 docs/02 §12.3。鉴权 verify_token。
底层 chat_store roleplay block 三层(物理隔离,不进 get_history);评分联动 score.service 驱动 reverse_infer。

路由(prefix /api/v1):
  POST   /roleplay/{oid}/sessions            新建会话(关当前open+开新block)
  GET    /roleplay/{oid}/sessions            列会话(各block元数据+msg_count,按start_ts倒序)
  POST   /roleplay/{oid}/messages            录单条 {role, content, score_base?}
  POST   /roleplay/{oid}/messages/batch      批量录连发 {items:[{role,content,score_base?}]}
  GET    /roleplay/{oid}/messages            列样本(block_id 可选过滤;完整字段含 score)
  PUT    /roleplay/{oid}/messages/{mid}      改单条 {content}
  PATCH  /roleplay/{oid}/messages/{mid}/score 改 roleplay 评分 {score_base}(联动反推样本队列)
  DELETE /roleplay/{oid}/messages/{mid}      删单条(→neg 队列 + 清 score 样本)
  POST   /roleplay/{oid}/extract             把训练样本抽成 long_term 记忆(手动触发,复用 encoder)

作者: 李文煜
日期: 2026-06-30

2026-07-05
变更说明：
  1. 多会话管理:新增 POST/GET /roleplay/{oid}/sessions(每段 block=一个训练会话)
  2. 评分联动反推:append 加 score_base 参数 + PATCH messages/{mid}/score;assistant 评分按阈值
     写 pos/neg 样本队列(复用 score.service),reverse_infer 零改动即读 roleplay 样本
  3. list messages 加 block_id 过滤(只列选中会话)

2026-07-07
变更说明：
  1. 新增 POST /roleplay/{oid}/extract:roleplay 训练样本 → long_term 记忆抽取(手动触发),
     复用 encoder.extract_facts_batch(过滤 system 旁白 + 每 12 条分批 + 防幻觉铁律),
     走 coordinator.upsert_facts_batch 写入(source='roleplay',不升级 core,天然防污染)。
     用于不经过 QQ 对话直接在后端创造记忆,服务于人设反推/记忆召回
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from api._auth import verify_token
from core.config import settings
from storage.redis_client import get_redis
from storage import chat_store

router = APIRouter(prefix="/api/v1", tags=["roleplay"])

_VALID_ROLES = ("user", "assistant", "system")


@router.post("/roleplay/{oid}/sessions", dependencies=[Depends(verify_token)])
async def create_session(oid: str):
    """新建会话:关闭当前 open roleplay block(若有)+ 开新 open block。返回新 block 元数据。"""
    redis = await get_redis()
    block = await chat_store.new_roleplay_block(redis, oid)
    return block


@router.get("/roleplay/{oid}/sessions", dependencies=[Depends(verify_token)])
async def list_sessions(oid: str):
    """列会话(各 block 元数据 + msg_count,按 start_ts 倒序)。每段=一个训练会话。"""
    redis = await get_redis()
    return await chat_store.list_roleplay_blocks(redis, oid)


@router.post("/roleplay/{oid}/messages", dependencies=[Depends(verify_token)])
async def add_message(oid: str, body: dict = Body(default={})):
    """录单条 roleplay 样本。body: {role: user|assistant|system, content, score_base?}。
    score_base(可选,仅 assistant 角色有反推意义):0-100,写 msg.score + 联动 pos/neg 样本队列。"""
    role = body.get("role", "user")
    content = (body.get("content") or "").strip()
    if role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {_VALID_ROLES}")
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    score_base = body.get("score_base")
    if score_base is not None:
        try:
            score_base = int(score_base)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="score_base must be int")
    redis = await get_redis()
    mid = await chat_store.append_roleplay_message(
        redis, oid, role=role, content=content, score_base=score_base)
    return {"mid": mid}


@router.post("/roleplay/{oid}/messages/batch", dependencies=[Depends(verify_token)])
async def add_batch(oid: str, body: dict = Body(default={})):
    """批量录 roleplay(同 open block 连发)。body: {items:[{role, content, score_base?}]}。受 takeover_batch_max 截断。"""
    items = body.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="items required")
    for it in items:
        if it.get("role") not in _VALID_ROLES or not (it.get("content") or "").strip():
            raise HTTPException(status_code=400, detail="each item needs valid role and content")
    items = items[:settings.takeover_batch_max]
    redis = await get_redis()
    mids = await chat_store.append_roleplay_batch(redis, oid, items=items)
    return {"mids": mids, "count": len(mids)}


@router.get("/roleplay/{oid}/messages", dependencies=[Depends(verify_token)])
async def list_messages(oid: str,
                        block_id: str = Query(default=""),
                        limit: int = Query(default=1000, ge=1, le=5000)):
    """列 roleplay 样本(完整字段含 score)。block_id 指定只列该会话;否则跨所有会话。按 ts 正序。"""
    redis = await get_redis()
    return {"object_id": oid, "messages": await chat_store.list_roleplay(
        redis, oid, block_id=block_id or None, limit=limit)}


@router.put("/roleplay/{oid}/messages/{mid}", dependencies=[Depends(verify_token)])
async def update_message(oid: str, mid: str, body: dict = Body(default={})):
    """改单条 roleplay 内容(→ status=edited)。body: {content}"""
    content = body.get("content")
    if content is None:
        raise HTTPException(status_code=400, detail="content required")
    redis = await get_redis()
    hit = await chat_store.update_roleplay(redis, oid, mid, content)
    if not hit:
        raise HTTPException(status_code=404, detail="message not found")
    return {"updated": True}


@router.patch("/roleplay/{oid}/messages/{mid}/score", dependencies=[Depends(verify_token)])
async def set_score(oid: str, mid: str, body: dict = Body(default={})):
    """改 roleplay 消息评分(2026-07-05)。body: {score_base: int 0-100}。
    重写 msg.score + 调整 pos/neg 样本队列(清旧按新分归类,驱动 reverse_infer)。"""
    if "score_base" not in body:
        raise HTTPException(status_code=400, detail="score_base required")
    try:
        score_base = int(body["score_base"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="score_base must be int")
    redis = await get_redis()
    data = await chat_store.set_roleplay_score(redis, oid, mid, score_base)
    if data is None:
        raise HTTPException(status_code=404, detail="message not found")
    return data


@router.delete("/roleplay/{oid}/messages/{mid}", dependencies=[Depends(verify_token)])
async def delete_message(oid: str, mid: str):
    """删单条 roleplay(→neg 队列作训练负信号 + 清 score 样本队列该 mid,物理删)"""
    redis = await get_redis()
    hit = await chat_store.delete_roleplay(redis, oid, mid)
    if not hit:
        raise HTTPException(status_code=404, detail="message not found")
    return {"deleted": True}


@router.delete("/roleplay/blocks/{block_id}", dependencies=[Depends(verify_token)])
async def delete_session(block_id: str):
    """物理删单个 roleplay 会话(block + 其全部消息,2026-07-06 训练样本删会话)。
    删前清各消息 score 样本(评分联动过的)。返回 {deleted_msgs}。"""
    redis = await get_redis()
    r = await chat_store.delete_roleplay_block(redis, block_id)
    return {"deleted": True, **r}


@router.post("/roleplay/{oid}/extract", dependencies=[Depends(verify_token)])
async def extract_to_memory(oid: str, body: dict = Body(default={})):
    """把 roleplay 训练样本抽成 long_term 记忆(手动触发,2026-07-07)。
    body: {block_id?}。取该会话(缺省全部)的 roleplay 消息,复用 encoder.extract_facts_batch
    抽事实(过滤 system 旁白 + 每 12 条分批 + 防幻觉铁律),批量写入 long_term
    (source='roleplay',走 upsert_facts_batch 不升级 core,天然防 core 污染)。
    返回 {extracted, written, skipped_dup, written_mids}。
    幂等:重复触发靠语义去重兜底(全部命中 skipped_dup,不产生新事实,access_count 微涨)。"""
    from core.config import settings
    from memory.roleplay_extract import extract_roleplay_facts
    from memory.coordinator import get_memory_coordinator

    redis = await get_redis()
    block_id = body.get("block_id") or None
    coord = await get_memory_coordinator()
    # 2026-07-07 拟人化:取角色对用户称呼,encoder 用具体称呼抽记忆(如"煜君喜欢动漫")
    from persona.store import get_object_persona_id, get_persona
    _pid = await get_object_persona_id(redis, oid)
    _card = await get_persona(redis, _pid)
    user_alias = _card.user_alias if _card else ""
    facts = await extract_roleplay_facts(
        redis, oid, block_id=block_id,
        llm=coord.llm, model=settings.memory_summary_model or "",
        user_alias=user_alias)
    result = await coord.upsert_facts_batch(oid, facts)
    return {"extracted": len(facts), **result}
