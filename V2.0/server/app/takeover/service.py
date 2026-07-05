"""
代人聊天应用层服务(M8)
编排代答产出全链路:takeover_store 出队 → chat_store 落 user+proxy 消息 → score_reply 评分
→ memory on_turn_complete 记忆编码 → mood apply_emotion → _deliver 下发 QQ(被动优先降级主动)。
对应 docs/01 §11 / docs/02 §8.2(批量连发)/§12.4。纯应用层(无 HTTP),便于单测。

异常边界:出队/落消息硬失败(抛 TakeoverNotFound);评分/记忆/心情/下发软失败(try 吞,日志,不阻塞)。
消息落库后不可回滚(管理员已手打,回滚丢训练数据);下发失败标记 delivered=False 供面板重试。

作者: 李文煜
日期: 2026-06-30

2026-06-30
变更说明：
  1. M8 新建 takeover service:resolve_and_deliver(单条全链路)/resolve_and_deliver_batch(批量)/
     _deliver(被动优先降级主动)/TakeoverNotFound
"""
import logging
import time

import httpx

from core.config import settings
from storage import takeover_store, chat_store
from pipeline.context import MessageContext

logger = logging.getLogger(__name__)


class TakeoverNotFound(Exception):
    """代答 pending 不存在/已过期/不匹配(REST 转 404)"""

    def __init__(self, pid):
        self.pid = pid
        super().__init__(f"pending not found: {pid}")


async def _resolve_persona(redis, oid: str):
    """解析对象绑定的 PersonaCard(未绑定兜底默认人设)。"""
    from persona.store import get_object_persona_id, get_persona, get_default_persona
    pid = await get_object_persona_id(redis, oid)
    card = await get_persona(redis, pid)
    if card is None:
        card = await get_default_persona(redis)
    return card


async def _deliver(redis, oid: str, content: str, *, msg_id: str, msg_seq: int, pid: str) -> dict:
    """下发 QQ:被动回复优先(带 msg_id,60min 窗口省月配额),QQ 拒绝(超时/超次)降级主动(msg_id="")。
    都失败返回 {delivered:False}(消息已落库不回滚)。返回 {delivered, mode}。"""
    delivered = False
    mode = ""
    from qq.api_client import send_c2c_message
    # content 是 admin 手打代答(人类产出),显式 human_authored=True 跳过出站守卫(#3)——
    # 守卫针对机器产出(LLM/工具)的错误文本泄漏;admin 文本即使含错误模式关键词也应原样发(如转述日志给用户)
    if msg_id:   # 1) 被动回复(msg_id 非空,省月配额)
        try:
            await send_c2c_message(oid, content, msg_id=msg_id, msg_seq=msg_seq, human_authored=True)
            delivered, mode = True, "passive"
        except httpx.HTTPStatusError as e:
            logger.warning("代答被动回复被拒(超时/超次) oid=%s pid=%s status=%s,降级主动",
                           oid, pid, e.response.status_code)
        except Exception as e:
            logger.warning("代答被动回复异常 oid=%s pid=%s: %s", oid, pid, e)
    if not delivered:   # 2) 降级主动消息(msg_id="",耗月配额)
        try:
            await send_c2c_message(oid, content, msg_id="", msg_seq=msg_seq, human_authored=True)
            delivered, mode = True, "active"
        except httpx.HTTPStatusError as e:
            logger.error("代答主动消息也失败(配额尽?) oid=%s pid=%s status=%s",
                         oid, pid, e.response.status_code)
        except Exception as e:
            logger.error("代答主动消息异常 oid=%s pid=%s: %s", oid, pid, e)
    return {"delivered": delivered, "mode": mode}


async def resolve_and_deliver(redis, oid: str, pid, answer: str, *, persona_card=None) -> dict:
    """代答单条全链路(管理员手打 answer 下发用户)。
    出队 → persona 解析 → [统一副作用链 run_post_reply_chain: 落 user+proxy 消息 → 评分 → 记忆编码(sync)]
    → msg_seq → 心情 → 下发 QQ。副作用链与 pipeline 共用(架构 #1,消除双份编排);
    落消息前硬失败抛 TakeoverNotFound,其后各步软失败不阻塞。返回 {pid, proxy_mid, delivered, mode, score?}。"""
    # A. 出队(硬失败:pending 不存在/过期/不匹配)
    pending = await takeover_store.resolve(redis, oid, pid)
    if pending is None:
        raise TakeoverNotFound(pid)
    user_text = pending.get("user_text", "")
    msg_id = pending.get("msg_id", "")
    real_pid = pending.get("pid", "")
    base_ts = int(pending.get("created_ts", 0) or 0) or int(time.time() * 1000)

    # C. persona_card 解析(软失败,降级 None;score 评分基准)—— 先于副作用链
    if persona_card is None:
        try:
            persona_card = await _resolve_persona(redis, oid)
        except Exception:
            logger.exception("代答 persona 解析失败 oid=%s", oid)
            persona_card = None

    # B+E+F 统一回合后副作用链(架构 #1,与 pipeline 共用):
    #   save(user+proxy 同 block 递增 ts)→ score(mood=None 读 get_mood, provider="")→ memory(sync await)
    # mood_update 留在链后调(takeover 时序=memory 后,与 reply_text 修改无耦合)
    from pipeline.stages import run_post_reply_chain
    ctx = MessageContext(object_id=oid, user_text=user_text, reply_text=answer,
                         persona_card=persona_card, created_ts=base_ts)
    score = await run_post_reply_chain(ctx, redis,
                                       reply_sender="proxy", reply_source="proxy",
                                       user_ts=base_ts, reply_ts=base_ts + 1,
                                       score_mood_value=None, score_provider="",
                                       await_memory=True)
    proxy_mid = ctx.reply_mid   # stage_save 写入(proxy 消息 mid)

    # D. msg_seq(per-oid 递增,防 QQ 同 msg_id+msg_seq 去重)—— deliver 用
    msg_seq = await takeover_store.next_msg_seq(redis, oid)

    # G. 心情更新(软失败:按代答回复关键词调整 mood)
    try:
        from mood.service import apply_emotion
        await apply_emotion(redis, oid, answer)
    except Exception:
        logger.exception("代答 apply_emotion 失败 oid=%s", oid)

    # H. 下发 QQ(独立环节,失败标记不回滚已落库消息;面板可重试)
    deliver = await _deliver(redis, oid, answer, msg_id=msg_id, msg_seq=msg_seq, pid=real_pid)
    await takeover_store.mark_delivered(redis, oid, real_pid, deliver)

    result = {"pid": real_pid, "proxy_mid": proxy_mid,
              "delivered": deliver["delivered"], "mode": deliver["mode"]}
    if score is not None:
        result["score"] = score.get("score")
    return result


async def resolve_and_deliver_batch(redis, oid: str, items: list, *, persona_card=None) -> dict:
    """批量代答(队列多条 pending 一次清空)。items=[{pid?, answer}],逐条 resolve_and_deliver,
    每条独立容错(一条失败不阻塞其他)。受 takeover_batch_max 截断。返回 {results, success, truncated}。"""
    raw_len = len(items)
    items = items[:settings.takeover_batch_max]
    truncated = raw_len > len(items)
    results = []
    success = 0
    for item in items:
        try:
            r = await resolve_and_deliver(redis, oid, item.get("pid"),
                                          item.get("answer", ""), persona_card=persona_card)
            results.append({"ok": True, **r})
            success += 1
        except TakeoverNotFound as e:
            results.append({"ok": False, "error": "not_found", "pid": e.pid})
        except Exception as e:
            logger.exception("代答 batch 单条失败 oid=%s", oid)
            results.append({"ok": False, "error": str(e)})
    return {"results": results, "success": success, "truncated": truncated}
