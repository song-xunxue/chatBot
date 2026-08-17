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
  2. 修分段:msg_seq 递增(QQ 同 msg_id 必须不同 msg_seq,否则第2段起返400)+ 加 on_before_llm 思考延迟(可配 reply_delay_min/max_ms)
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
    """回复节奏控制:on_before_llm 思考延迟(收到后随机等待再回,缓解回复过快)
    + on_message_out 分段多气泡发送。仅分段受 qq_msg_id 门控(被动回复)。"""

    async def on_before_llm(self, ctx):
        """回复前思考延迟:LLM 前随机等待(模拟看完消息再打字,缓解回复过快)。
        delay_max<=0 禁用;范围 [min,max] ms 随机,面板可配。"""
        params = await self.get_params(ctx.object_id)
        dmin = float(params.get("reply_delay_min_ms", 3000)) / 1000.0
        dmax = float(params.get("reply_delay_max_ms", 5000)) / 1000.0
        if dmax > 0:
            await asyncio.sleep(random.uniform(dmin, max(dmax, dmin)))
        return HookResult.CONTINUE

    async def on_message_out(self, ctx):
        if getattr(ctx, "reply_sent", False):
            return HookResult.CONTINUE  # 已由其他插件处理(如 tts_reply 发语音),跳过分段
        params = await self.get_params(ctx.object_id)
        max_seg = int(params.get("max_segments", 3))
        min_seg = int(params.get("min_segments", 2))
        segments = split_reply(ctx.reply_text, max_seg, min_seg)
        if len(segments) <= 1:
            return HookResult.CONTINUE             # 段数不足,不拆,交 webhook 单条发
        msg_id = getattr(ctx, "qq_msg_id", "")
        if not msg_id:
            return HookResult.CONTINUE             # 无 msg_id(非被动回复),不处理
        from adapter import get_current_adapter   # V3.0:平台适配器(official/onebot 配置驱动)
        adapter = await get_current_adapter()
        interval_min = float(params.get("interval_min_ms", 500)) / 1000.0
        interval_max = float(params.get("interval_max_ms", 1500)) / 1000.0
        for i, seg in enumerate(segments):
            if i > 0:
                await asyncio.sleep(random.uniform(interval_min, interval_max))   # 段间随机间隔(模拟打字)
            try:
                # msg_seq 递增(1,2,3...):official 被动回复同 msg_id 必须用不同 msg_seq(否则 400);
                # onebot 忽略 msg_seq(主动直发无窗口概念)。分段发送的关键在 official 侧。
                await adapter.send_text(ctx.object_id, seg, msg_id=msg_id, msg_seq=i + 1)
            except Exception:
                # 兜底:某段失败 → 剩余段(含当前)写回 reply_text,清 reply_sent,让入口单条兜底发
                logger.exception("continuous_send 第 %d 段下发失败,剩余交入口兜底 oid=%s",
                                 i + 1, ctx.object_id)
                ctx.reply_text = "\n".join(segments[i:])
                ctx.reply_sent = False
                return HookResult.CONTINUE
        ctx.reply_sent = True                      # 全部发完,标记 webhook 跳过默认单条下发
        return HookResult.CONTINUE
