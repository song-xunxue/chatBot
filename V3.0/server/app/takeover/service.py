"""
对话控制应用层服务(2026-09-13 静默模式重构)
职责收敛为三件事:
  ① record_manual_reply —— 管理员经 QQ(清浔号)手动回复的记录:message_sent 上报触发,
     直接落 proxy 消息(source='manual')+ 恒正评分(黄金样本)+ 心情 + 写手动静默期;
  ② send_proactive —— 面板主动发送(以清浔身份推消息给用户,落 proxy + 下发);
  ③ _deliver —— 下发 QQ(TTS 开关/被动降级主动,send_proactive 复用)。
V2.0 时代的待答队列代答链(resolve_and_deliver/batch/skip/clear)已随队列删减移除。

异常边界:落库硬失败上抛;评分/心情软失败(try 吞,不阻塞)。

作者: 李文煜
日期: 2026-06-30

2026-06-30
变更说明：
  1. M8 新建 takeover service:resolve_and_deliver(单条全链路)/resolve_and_deliver_batch(批量)/
     _deliver(被动优先降级主动)/TakeoverNotFound

2026-07-05
变更说明：
  1. 新增 send_proactive(主动发送,不依赖 pending;落 proxy 消息 + 下发 QQ)

2026-09-07
变更说明：
  1. record_manual_reply(手动回复记录:drain 队列+配对落库+恒正样本)+skip_and_archive/clear_queue

2026-09-13
变更说明：
  1. 队列删减重构:删队列代答链(resolve/batch/skip/clear/drain);record_manual_reply 改为
     直接落库(静默期/静默模式下用户消息已由 ws_client 直录入库,无需配对合并)——
     append proxy(manual) + score_reply(force_positive 恒正 source='manual') + apply_emotion
     + set_silence(手动静默期,自动模式下 AI 暂闭嘴 takeover_manual_silence_min 分钟)
"""
import logging
import time

from core.config import settings
from storage import chat_store, takeover_store

logger = logging.getLogger(__name__)


async def _resolve_persona(redis, oid: str):
    """解析对象绑定的 PersonaCard(未绑定兜底默认人设)。"""
    from persona.store import get_object_persona_id, get_persona, get_default_persona
    pid = await get_object_persona_id(redis, oid)
    card = await get_persona(redis, pid)
    if card is None:
        card = await get_default_persona(redis)
    return card


async def _read_tts_voice_params(oid: str):
    """从 tts_reply 插件 config 读 voice/speed/gain/emotion_enable(共享 bot 音色)。
    插件未加载/异常用默认(claire/1.0/0.0/True)。代答 TTS 复用插件音色设置,避免重复配置。"""
    try:
        from plugins import get_plugin_manager
        mgr = get_plugin_manager()
        if mgr and "tts_reply" in mgr.list_loaded():
            p = await mgr.get_params("tts_reply", oid)
            return (p.get("voice") or "claire",
                    float(p.get("speed", 1.0)),
                    float(p.get("gain", 0.0)),
                    bool(p.get("emotion_enable", True)))
    except Exception:
        logger.exception("读 tts_reply 插件 voice 参数失败 oid=%s,用默认", oid)
    return "claire", 1.0, 0.0, True


async def _deliver(redis, oid: str, content: str, *, msg_id: str, msg_seq: int, pid: str) -> dict:
    """下发 QQ:代答 TTS 开启则语音优先(可选先文本);否则被动回复优先(带 msg_id)降级主动(msg_id="")。
    都失败返回 {delivered:False}(消息已落库不回滚)。返回 {delivered, mode}。"""
    # 代答 TTS 开关(M-tts):启用则合成语音发(复用 tts_reply 插件音色);失败/空产出降级文本
    tts_cfg = await takeover_store.get_tts_config(redis, oid)
    if tts_cfg.get("enable"):
        voice, speed, gain, emo = await _read_tts_voice_params(oid)
        from modality.tts import resolve_voice, send_voice_reply
        voice = await resolve_voice(redis, oid, voice)   # 优先克隆 uri(面板「设为当前」),回退预设
        vr = await send_voice_reply(oid, content, msg_id=msg_id, msg_seq=msg_seq,
                                    voice=voice, speed=speed, gain=gain,
                                    emotion_enable=emo,
                                    send_text_also=bool(tts_cfg.get("send_text_also", False)),
                                    human_authored=True)  # admin 代答文本不过守卫
        if vr and vr.get("delivered"):
            return {"delivered": True, "mode": vr["mode"]}
        # TTS 失败/空 → 降级文本下发(下方)
    delivered = False
    mode = ""
    from adapter import get_current_adapter
    adapter = await get_current_adapter()
    # content 是 admin 手打(人类产出),显式 human_authored=True 跳过出站守卫(#3)——
    # 守卫针对机器产出(LLM/工具)的错误文本泄漏;admin 文本即使含错误模式关键词也应原样发
    if msg_id:   # 1) 被动回复(msg_id 非空,省月配额;onebot 忽略 msg_id 等价直发)
        try:
            await adapter.send_text(oid, content, msg_id=msg_id, msg_seq=msg_seq, human_authored=True)
            delivered, mode = True, "passive"
        except Exception as e:
            logger.warning("代答被动回复异常 oid=%s pid=%s: %s,降级主动", oid, pid, e)
    if not delivered:   # 2) 降级主动消息(msg_id="",onebot 无配额概念)
        try:
            await adapter.send_text(oid, content, msg_id="", msg_seq=msg_seq, human_authored=True)
            delivered, mode = True, "active"
        except Exception as e:
            logger.error("代答主动消息异常 oid=%s pid=%s: %s", oid, pid, e)
    return {"delivered": delivered, "mode": mode}


async def send_proactive(redis, oid: str, content: str) -> dict:
    """主动发送(管理员经面板以清浔身份推消息给用户)。
    落 proxy 消息(进 live 历史,供后续 LLM 上下文引用)+ 下发 QQ。
    不走评分/记忆编码副作用链(无 user 回合,评分无意义);proxy 消息本身进 chat history 已够记忆引用。
    返回 {proxy_mid, delivered, mode}。"""
    base_ts = int(time.time() * 1000)
    proxy_mid = await chat_store.append_message(
        redis, oid, sender="proxy", content=content, source="proxy", ts=base_ts)
    msg_seq = await takeover_store.next_msg_seq(redis, oid)
    deliver = await _deliver(redis, oid, content, msg_id="", msg_seq=msg_seq, pid="proactive")
    return {"proxy_mid": proxy_mid, "delivered": deliver["delivered"], "mode": deliver["mode"]}


async def record_manual_reply(redis, oid: str, content: str, *, sent_ts: int = 0) -> dict:
    """手动回复记录(2026-09-13 重构,NapCat message_sent 上报触发,ws_client._handle_manual_sent 调)。
    管理员直接用角色 QQ 号(手机端等)手动回复用户——消息已亲手发出,本函数只做记录,绝不再下发。
      ① 落 proxy 消息(source='manual',进 live 历史;静默期/静默模式下用户消息已由
         ws_client 直录,历史自然相邻成对,无需旧版的队列合并)
      ② 恒正评分:score_reply(force_positive=True)——LLM 四元组照算(展示/健康度),
         样本恒正 source='manual' score=100(黄金标准;占位 [语音] 等不入样本)
      ③ 心情 apply_emotion(软失败)
      ④ 写手动静默期 set_silence(自动模式下 AI 暂闭嘴 takeover_manual_silence_min 分钟,
         管理员连续手动聊时 AI 不插嘴;静默模式本身已静默,写了也无害)
    返回 {proxy_mid, scored}。"""
    sent_ts = sent_ts or int(time.time() * 1000)
    proxy_mid = await chat_store.append_message(
        redis, oid, sender="proxy", content=content, source="manual", ts=sent_ts)

    # 恒正评分(黄金样本;软失败不阻塞)
    scored = False
    try:
        persona_card = await _resolve_persona(redis, oid)
        from score.service import score_reply
        quad = await score_reply(redis, oid, content, persona_card, proxy_mid,
                                 mood_value=None, provider_name="", force_positive=True)
        scored = quad is not None   # 样本在 score_reply 内恒收(含 LLM 失败时)
    except Exception:
        logger.exception("手动回复评分失败 oid=%s(样本可能未收,不影响落库)", oid)

    # 心情(软失败)
    try:
        from mood.service import apply_emotion
        await apply_emotion(redis, oid, content)
    except Exception:
        logger.exception("手动回复 apply_emotion 失败 oid=%s", oid)

    # 手动静默期(0=禁用)
    try:
        await takeover_store.set_silence(redis, oid, settings.takeover_manual_silence_min)
    except Exception:
        logger.exception("写手动静默期失败 oid=%s", oid)
    return {"proxy_mid": proxy_mid, "scored": scored}
