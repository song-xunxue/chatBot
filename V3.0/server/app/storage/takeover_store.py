"""
对话控制存储(2026-09-13 静默模式重构)
原 V2.0 的 per-object FIFO 待答队列已随"队列删减"移除——现语义:
  mychat:takeover:enabled:{oid}   String "1"  AI 静默模式(开=AI 不自动回复,全手动)
  mychat:takeover:silence:{oid}   String "1" EX N  手动静默期(自动模式下手动回复后 AI 暂闭嘴,
                                  Redis TTL 即时间窗,过期自动恢复;写入方 record_manual_reply)
  mychat:takeover:msgseq:{oid}    INCR          per-oid 发送序(official 时代防重;onebot 忽略,保留无害)
  mychat:takeover:tts:{oid}       String(JSON)  代答 TTS 两开关

作者: 李文煜
日期: 2026-06-30

2026-06-30
变更说明：
  1. M8 新建 takeover_store:per-object FIFO 队列(替 V1.0 单 active 覆盖丢消息)
     + 孤儿 pid 惰性清理(pending TTL 过期)+ msgseq per-oid 防 QQ 去重

2026-09-07
变更说明：
  1. drain_queue/skip_mark/requeue(手动回复消化/跳过归档/回灌兜底)

2026-09-13
变更说明：
  1. 队列删减(用户拍板):删 FIFO 队列/pending/resolution 全套——代答模式语义改为
     "AI 静默开关";新增 is_silenced/set_silence(手动静默期,Redis TTL 实现时间窗);
     手动回复改为直接落库(见 takeover.service.record_manual_reply)
"""
import json

from redis.asyncio import Redis

from core.config import settings

_K_ENABLED = "mychat:takeover:enabled:{oid}"
_K_SILENCE = "mychat:takeover:silence:{oid}"
_K_MSGSEQ = "mychat:takeover:msgseq:{oid}"


# ================ AI 静默开关(原代答模式开关,语义更名) ================

async def is_enabled(redis: Redis, oid: str) -> bool:
    """AI 静默模式是否开启(开=AI 不自动回复,由管理员 QQ 手动回复/面板发送)"""
    return await redis.get(_K_ENABLED.format(oid=oid)) == "1"


async def set_enabled(redis: Redis, oid: str, enabled: bool) -> None:
    """开/关 AI 静默模式"""
    key = _K_ENABLED.format(oid=oid)
    if enabled:
        await redis.set(key, "1")
    else:
        await redis.delete(key)


# ================ 手动静默期(自动模式下,手动回复后 AI 暂闭嘴) ================

async def is_silenced(redis: Redis, oid: str) -> bool:
    """手动静默期是否生效(键存在即生效;TTL 到点自动失效,免清扫)"""
    return await redis.exists(_K_SILENCE.format(oid=oid)) > 0


async def set_silence(redis: Redis, oid: str, minutes: int) -> None:
    """写手动静默期(TTL=minutes 分钟;minutes<=0 清除)。手动回复落库后调用,
    窗口内该用户的后续消息直接入库不触发 LLM(管理员连续手动聊时 AI 不插嘴)。"""
    key = _K_SILENCE.format(oid=oid)
    if minutes <= 0:
        await redis.delete(key)
        return
    await redis.set(key, "1", ex=minutes * 60)


# ================ 发送序(official 时代防同 msg_id+seq 去重;onebot 忽略,保留无害) ================

async def next_msg_seq(redis: Redis, oid: str) -> int:
    """取下一个 per-oid 发送序(INCR)"""
    return await redis.incr(_K_MSGSEQ.format(oid=oid))


# ================ 代答 TTS 开关(M-tts,2026-08-04)================

_K_TTS = "mychat:takeover:tts:{oid}"


async def get_tts_config(redis: Redis, oid: str) -> dict:
    """代答 TTS 配置 {enable, send_text_also};未设置返空 dict(等价 enable=False,纯文本代答)"""
    raw = await redis.get(_K_TTS.format(oid=oid))
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def set_tts_config(redis: Redis, oid: str, enable: bool, send_text_also: bool) -> None:
    """写代答 TTS 配置(整 JSON 替换)"""
    await redis.set(
        _K_TTS.format(oid=oid),
        json.dumps({"enable": bool(enable), "send_text_also": bool(send_text_also)}, ensure_ascii=False),
    )
