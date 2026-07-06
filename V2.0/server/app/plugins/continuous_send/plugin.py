"""
continuous_send 插件(消息分段发送,2026-07-07)
on_message_out:按换行拆 reply_text 成多段,逐段 send_c2c_message 下发(多个气泡,像真人微信连发)。
不改 reply_text(save 仍存完整对话历史),发完设 ctx.reply_sent=True 让 webhook 跳过默认单条下发。
拆分/间隔/最大段数面板可配(config_schema)。失败兜底:某段下发失败则剩余写回 reply_text 交 webhook 单条发。

作者: 李文煜
日期: 2026-07-07

2026-07-07
变更说明：
  1. 新建 continuous_send:被动回复分段发送(按换行拆,逐段带随机间隔,多气泡)
"""
import asyncio
import logging
import random

from plugins.base import Plugin, HookResult

logger = logging.getLogger(__name__)


def split_reply(text: str, max_segments: int = 3, min_segments: int = 2) -> list[str]:
    """拆分回复为多段(纯函数,可单测)。
    按换行拆 + 过滤空行;段数 < min_segments 返回空(不拆,交单条发);
    段数 > max_segments 合并尾部到第 max 段(保留全部内容,不截断)。"""
    if not text:
        return []
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]            # 过滤空行
    if len(lines) < min_segments:
        return []                                 # 段数不足,不拆(调用方单条发)
    if len(lines) <= max_segments:
        return lines
    # 超过 max:前 max-1 段独立,尾部合并到第 max 段(保留换行,内容不丢)
    head = lines[: max_segments - 1]
    tail = "\n".join(lines[max_segments - 1:])
    return head + [tail]


class ContinuousSendPlugin(Plugin):
    """消息分段发送:on_message_out 拆回复 → 逐段下发 → 多气泡。
    仅处理 QQ 被动回复(ctx.qq_msg_id 非空);代答主动发送无 msg_id 不处理。"""

    async def on_message_out(self, ctx):
        params = await self.get_params(ctx.object_id)
        max_seg = int(params.get("max_segments", 3))
        min_seg = int(params.get("min_segments", 2))
        segments = split_reply(ctx.reply_text, max_seg, min_seg)
        if len(segments) <= 1:
            return HookResult.CONTINUE             # 段数不足,不拆,交 webhook 单条发
        msg_id = getattr(ctx, "qq_msg_id", "")
        if not msg_id:
            return HookResult.CONTINUE             # 无 msg_id(非被动回复),不处理
        from qq.api_client import send_c2c_message
        interval_min = float(params.get("interval_min_ms", 500)) / 1000.0
        interval_max = float(params.get("interval_max_ms", 1500)) / 1000.0
        for i, seg in enumerate(segments):
            if i > 0:
                await asyncio.sleep(random.uniform(interval_min, interval_max))   # 段间随机间隔(模拟打字)
            try:
                await send_c2c_message(ctx.object_id, seg, msg_id=msg_id)
            except Exception:
                # 兜底:某段失败 → 剩余段(含当前)写回 reply_text,清 reply_sent,让 webhook 单条兜底发
                logger.exception("continuous_send 第 %d 段下发失败,剩余交 webhook 兜底 oid=%s",
                                 i + 1, ctx.object_id)
                ctx.reply_text = "\n".join(segments[i:])
                ctx.reply_sent = False
                return HookResult.CONTINUE
        ctx.reply_sent = True                      # 全部发完,标记 webhook 跳过默认单条下发
        return HookResult.CONTINUE
