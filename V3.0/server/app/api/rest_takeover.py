"""
对话控制 REST 接口(2026-09-13 队列删减重构)
V2.0 的待答队列端点族(queue/answer/answer-batch/skip/queue/clear)已移除,现语义:

路由(prefix /api/v1):
  POST /takeover/{oid}/toggle          开关「AI 静默模式」(开=AI 不自动回复,全手动)
  GET  /takeover/{oid}/status          开关状态
  POST /takeover/{oid}/send            主动发送(以清浔身份推消息,落 proxy + 下发 QQ)
  GET/PUT /takeover/{oid}/tts_config   代答 TTS 两开关(语音合成参数复用 tts_reply 插件)

自动模式下管理员经 QQ 手动回复后,自动进入手动静默期(takeover_manual_silence_min
分钟内 AI 不自动回复),无需任何面板操作。

作者: 李文煜
日期: 2026-06-30

2026-08-18
变更说明：
  1. V3.0 oid 语义=QQ 号:全部端点前置 _require_qq_oid 校验(修线上 oid=default 下发失败)

2026-09-13
变更说明：
  1. 队列删减(用户拍板):删 queue/answer/answer-batch/skip/queue/clear 端点;
     toggle 语义更名「AI 静默模式」;新增静默期说明(纯文档,无新端点)
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
    """开关「AI 静默模式」。body: {enabled: bool}。
    开=AI 不自动回复(全手动:QQ 手动回复或面板发送);关=自动回复
    (手动 QQ 回复后仍有 takeover_manual_silence_min 分钟静默窗,互不打扰)。"""
    _require_qq_oid(oid)
    enabled = bool(body.get("enabled"))
    redis = await get_redis()
    await takeover_store.set_enabled(redis, oid, enabled)
    return {"object_id": oid, "enabled": enabled}


@router.get("/takeover/{oid}/status", dependencies=[Depends(verify_token)])
async def status(oid: str):
    """AI 静默模式开关状态(队列已删减,不再有 queue_length)"""
    _require_qq_oid(oid)
    redis = await get_redis()
    return {"object_id": oid, "enabled": await takeover_store.is_enabled(redis, oid)}


@router.post("/takeover/{oid}/send", dependencies=[Depends(verify_token)])
async def send_proactive(oid: str, body: dict = Body(default={})):
    """主动发送(以清浔身份直接推消息给用户)。body: {content}。
    落 proxy 消息(进 live 历史)+ 下发 QQ。静默模式的主要面板触达途径。"""
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    _require_qq_oid(oid)
    redis = await get_redis()
    return await takeover_svc.send_proactive(redis, oid, content)


# —— 代答 TTS 开关(M-tts,2026-08-04):两开关逻辑同 tts_reply 插件;voice/speed/gain 复用插件 config ——

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
    """写代答 TTS 配置。body: {enable: bool, send_text_also: bool}。"""
    enable = bool(body.get("enable"))
    send_text_also = bool(body.get("send_text_also"))
    _require_qq_oid(oid)
    redis = await get_redis()
    await takeover_store.set_tts_config(redis, oid, enable, send_text_also)
    return {"object_id": oid, "enable": enable, "send_text_also": send_text_also}
