"""
sticker_plus 插件(自动配图)
on_message_out 回复发出前,按"心情档位过滤 + 描述词重叠 + 最近使用降权"从表情包库挑一张,
向 ctx.reply_text 末尾追加一个 [表情包: 描述] token(最多 1 张/条)——token 由出站 adapter
(onebot.send_text 经 sticker_store.split_reply_with_tokens)解析为真实表情包图片,且
on_message_out 在存历史前触发,token 随回复一并入历史/训练数据(OUTPUT_CONTRACT 机制)。
概率门可调(attach_prob 默认 0.35),插件默认关闭;文字表情渲染参数仅在 config_schema 暴露,
供 REST /api/v1/sticker/render 与后续使用,本插件不调用 render。

软失败原则:钩子体任何异常只记日志,恒返回 CONTINUE,不影响其他插件与主链路。

作者: 李文煜
日期: 2026-10-25

2026-10-25
变更说明：
  1. 新建 sticker_plus 插件:on_message_out 自动配图(排除链/概率门/心情档位/picker 挑选/
     追加 token/记 recent_usage 队列 + last_used 时间)
  2. 审查加固:参数显式判 None 再转型(面板存 null 时 float(None)/int(None) 抛 TypeError)、
     token 用已 strip 文本拼接、usage_window<=0 不写队列(与 picker 不降权口径一致)、
     修正 reply_sent 注释(只有 tts_reply(300) 等更早插件可能先置位)
"""
import logging
import random
from datetime import datetime

from mood.service import inject_hint   # 心情聚合口:返回 {mood, hint, label, kaomoji}
from plugins.base import HookResult, Plugin
from plugins.sticker_plus.picker import _K_RECENT_USAGE, pick_sticker
from plugins.sticker_plus.render import _K_LAST_USED   # Hash:文件名→最近使用 iso 时间(render.py own)
from storage.sticker_store import _REPLY_TOKEN_RE      # 出站 [表情包: 描述] token 正则(共享契约)

logger = logging.getLogger(__name__)


class StickerPlusPlugin(Plugin):
    """表情包增强:自动配图(on_message_out 追加 [表情包: 描述] token,最多 1 张/条)"""

    async def on_message_out(self, ctx):
        try:
            await self._maybe_attach(ctx)
        except Exception:
            # 软失败:配图是锦上添花,任何异常绝不阻断回复主链路(照 proactive_reply 风格)
            logger.exception("sticker_plus 处理异常 oid=%s(软失败,忽略)", ctx.object_id)
        return HookResult.CONTINUE

    async def _maybe_attach(self, ctx) -> None:
        params = await self.get_params(ctx.object_id)
        redis = self.pctx.redis
        reply_text = (ctx.reply_text or "").strip()
        # 排除链(每条跳过都带原因 debug,便于线上排查"为何没配图")
        if ctx.reply_sent:
            # 回复已被更早的插件发出(tts_reply(300) 已发语音置位;continuous_send(400) 在
            # 本插件(350)之后执行,不可能先置位),再改文本已无效
            logger.debug("sticker_plus 跳过:回复已被其他插件发送 oid=%s", ctx.object_id)
            return
        if not reply_text:
            # 空白回复/纯语音(文本为空),无从配图
            logger.debug("sticker_plus 跳过:回复文本为空 oid=%s", ctx.object_id)
            return
        if _REPLY_TOKEN_RE.search(reply_text):
            # 本条已有表情包 token(模型自己带了),最多 1 张/条,不再追加
            logger.debug("sticker_plus 跳过:本条已有表情包 token oid=%s", ctx.object_id)
            return
        # 概率门:默认 0.35;0=永不配图,1=每条必配(random() ∈ [0,1),>=prob 即跳过)。
        # 显式判 None 再转型:面板可能存入 null,float(None) 会抛 TypeError
        prob_raw = params.get("attach_prob")
        prob = float(prob_raw) if prob_raw is not None else 0.35
        if random.random() >= prob:
            logger.debug("sticker_plus 跳过:概率未命中(attach_prob=%.2f) oid=%s", prob, ctx.object_id)
            return
        # 当前心情档位 label:inject_hint 聚合口(无档位时 label="");失败当无心情,不阻断配图
        label = ""
        try:
            state = await inject_hint(redis, ctx.object_id)
            label = str((state or {}).get("label", ""))
        except Exception:
            logger.warning("sticker_plus 读取心情失败,按无心情处理 oid=%s", ctx.object_id, exc_info=True)
        # 窗口同样判 None 再转型;0/负值=不记使用(picker 视为不降权,与这里不写队列保持一致)
        window_raw = params.get("usage_window")
        usage_window = int(window_raw) if window_raw is not None else 10
        desc, fname, reason = await pick_sticker(
            redis, reply_text,
            mood_label=label,
            mood_keywords=str(params.get("mood_keywords", "") or ""),
            mood_weight_enable=bool(params.get("mood_weight_enable", True)),
            usage_window=usage_window,
        )
        if desc is None:
            logger.debug("sticker_plus 未配图:%s oid=%s", reason, ctx.object_id)
            return
        # 追加 token(独立成行,用已 strip 的文本拼,避免尾部空白多出空行;存历史前触发,
        # token 随回复入历史/训练数据)
        ctx.reply_text = f"{reply_text}\n[表情包: {desc}]"
        # 记使用:recent_usage 队列(picker 降权读)+ last_used 时间(REST list"最近使用"列)
        if usage_window > 0:
            await redis.lpush(_K_RECENT_USAGE, fname)   # lpush(键, 值):从队头插入,最新在前
            await redis.ltrim(_K_RECENT_USAGE, 0, usage_window - 1)   # ltrim:只保留窗口长度
        await redis.hset(_K_LAST_USED, fname, datetime.now().isoformat(timespec="seconds"))
        logger.info("自动配图追加表情包 oid=%s file=%s reason=%s", ctx.object_id, fname, reason)
