"""
代人聊天代答 REST 接口(M8):开关/状态/列队列/单条+批量代答/跳过。
对应 docs/02 §12.4。鉴权 verify_token(Header 或 query)。代答产出全链路在 takeover/service。

路由(prefix /api/v1):
  POST /takeover/{oid}/toggle          开关代答模式
  GET  /takeover/{oid}/status          开关状态 + 队列长度
  GET  /takeover/{oid}/queue           列 pending 队列(带孤儿过滤)
  POST /takeover/{oid}/answer          单条代答(pid 空取队首)
  POST /takeover/{oid}/answer/batch    批量代答(逐条下发 QQ)
  POST /takeover/{oid}/skip            跳过(队首或指定 pid;2026-09-07 起归档用户消息到历史)
  POST /takeover/{oid}/send            主动发送(不依赖 pending,管理员直接推消息给用户)
  POST /takeover/{oid}/queue/clear     一键清空(逐条归档到历史后清队,2026-09-07)

作者: 李文煜
日期: 2026-06-30

2026-07-05
变更说明：
  1. 面板改造:新增 POST /takeover/{oid}/send 主动发送端点(takeover 模式下面板主动触达用户,
     无需用户先发),委托 takeover_svc.send_proactive(落 proxy 消息 + 下发 QQ)

2026-08-18
变更说明：
  1. V3.0 oid 语义=QQ 号(纯数字):全部端点前置校验 _require_qq_oid,非数字(如 default/
     旧 openid)直接 400 明确报错——否则落到 onebot 适配器 int(oid) 才炸,面板只见"下发:失败"
     (修线上 oid=default 代答下发失败:invalid literal for int())

2026-09-07
变更说明：
  1. /skip 改调 skip_and_archive(跳过前用户消息落历史,不再是历史黑洞);
     新增 /queue/clear 一键清空(逐条归档+清队)
"""
from fastapi import APIRouter, Body, Depends, HTTPException

from api._auth import verify_token
from storage.redis_client import get_redis
from storage import takeover_store
from takeover import service as takeover_svc

router = APIRouter(prefix="/api/v1", tags=["takeover"])


def _require_qq_oid(oid: str) -> None:
    """校验 oid 为 QQ 号(纯数字)。V3.0 出站 user_id=int(oid),非数字必失败;
    提前 400 给出可操作提示(头部 oid 框填用户 QQ 号),替代静默 delivered=False。"""
    if not (oid and oid.isdigit()):
        raise HTTPException(
            status_code=400,
            detail=f"oid 必须为 QQ 号(纯数字),当前: {oid!r};请在面板头部 oid 框填用户 QQ 号后回车")


@router.post("/takeover/{oid}/toggle", dependencies=[Depends(verify_token)])
async def toggle(oid: str, body: dict = Body(default={})):
    """开关代答模式。body: {enabled: bool}"""
    _require_qq_oid(oid)
    enabled = bool(body.get("enabled"))
    redis = await get_redis()
    await takeover_store.set_enabled(redis, oid, enabled)
    return {"object_id": oid, "enabled": enabled}


@router.get("/takeover/{oid}/status", dependencies=[Depends(verify_token)])
async def status(oid: str):
    """代答开关状态 + 队列长度"""
    _require_qq_oid(oid)
    redis = await get_redis()
    return {
        "object_id": oid,
        "enabled": await takeover_store.is_enabled(redis, oid),
        "queue_length": await takeover_store.queue_length(redis, oid),
    }


@router.get("/takeover/{oid}/queue", dependencies=[Depends(verify_token)])
async def queue(oid: str):
    """列 pending 队列(FIFO 正序,带孤儿过滤)"""
    _require_qq_oid(oid)
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
    _require_qq_oid(oid)
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
    _require_qq_oid(oid)
    redis = await get_redis()
    return await takeover_svc.resolve_and_deliver_batch(redis, oid, items)


@router.post("/takeover/{oid}/skip", dependencies=[Depends(verify_token)])
async def skip(oid: str, body: dict = Body(default={})):
    """跳过(放弃代答)。body: {pid?}。pid 空跳队首。命中返 True。
    2026-09-07:跳过前用户消息归档到历史(用户说过的话不再凭空消失)。"""
    pid = body.get("pid") or None
    _require_qq_oid(oid)
    redis = await get_redis()
    return await takeover_svc.skip_and_archive(redis, oid, pid)


@router.post("/takeover/{oid}/queue/clear", dependencies=[Depends(verify_token)])
async def clear_queue(oid: str):
    """一键清空待答队列(2026-09-07):全部 pending 的用户消息逐条归档到历史(各自原始 ts)
    后清空队列。用于线上堆积清理/管理员批量放弃代答。返回 {cleared, archived}。"""
    _require_qq_oid(oid)
    redis = await get_redis()
    return await takeover_svc.clear_queue(redis, oid)


@router.post("/takeover/{oid}/send", dependencies=[Depends(verify_token)])
async def send_proactive(oid: str, body: dict = Body(default={})):
    """主动发送(不依赖 pending,管理员直接推消息给用户)。body: {content}。
    落 proxy 消息(进 live 历史)+ 下发 QQ。takeover 模式下 LLM 已被 webhook 拦截,
    此端点是面板主动触达用户的途径(用户无需先发消息)。"""
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    _require_qq_oid(oid)
    redis = await get_redis()
    return await takeover_svc.send_proactive(redis, oid, content)


# —— 代答 TTS 开关(M-tts,2026-08-04):两开关逻辑同 tts_reply 插件;voice/speed/gain/emotion 复用插件 config ——


@router.get("/takeover/{oid}/tts_config", dependencies=[Depends(verify_token)])
async def get_tts_config(oid: str):
    """代答 TTS 配置 {enable, send_text_also};未设置返全 False(纯文本代答)"""
    _require_qq_oid(oid)
    redis = await get_redis()
    cfg = await takeover_store.get_tts_config(redis, oid)
    return {"object_id": oid,
            "enable": bool(cfg.get("enable")),
            "send_text_also": bool(cfg.get("send_text_also"))}


@router.put("/takeover/{oid}/tts_config", dependencies=[Depends(verify_token)])
async def set_tts_config(oid: str, body: dict = Body(default={})):
    """写代答 TTS 配置。body: {enable: bool, send_text_also: bool}。
    enable=代答是否启用语音;send_text_also=启用时是否同发文本(默认 False 只语音,替换文本)。"""
    enable = bool(body.get("enable"))
    send_text_also = bool(body.get("send_text_also"))
    _require_qq_oid(oid)
    redis = await get_redis()
    await takeover_store.set_tts_config(redis, oid, enable, send_text_also)
    return {"object_id": oid, "enable": enable, "send_text_also": send_text_also}
