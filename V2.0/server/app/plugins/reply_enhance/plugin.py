"""
reply_enhance 插件(回复增强)
1) 输入累积(accumulate=true 时启用):on_message_in 把连续用户消息存入缓冲;
   on_before_llm 判断"攒够再回"——达 flush_count 或末条语义完整(句末标点)则合并 flush,否则 STOP 暂缓回复。
2) 输出合并:on_message_out 合并回复中的多余空行/碎片段,使回复更紧凑。

M6 从 V1.0 收敛到 V2.0(代码零改;Plugin 基类/EventBus/redis 一致)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M6 从 V1.0 收敛 reply_enhance 到 V2.0(零改;输入累积 + 输出合并)
"""
import json
import re

from plugins.base import Plugin, HookResult

_BUFFER_KEY = "mychat:replybuf:{oid}"   # 输入累积缓冲 Redis 键
_TERMINAL = re.compile(r"[。！？!?\.…]$")  # 句末标点(语义完整启发式)


def should_flush(buffer: list[dict], flush_count: int) -> bool:
    """flush 决策(纯函数,可单测):条数达上限 或 末条语义完整(句末标点)→True"""
    if not buffer:
        return True
    if len(buffer) >= flush_count:
        return True
    last = (buffer[-1].get("text", "") or "").strip()
    if _TERMINAL.search(last):
        return True
    return False


def merge_output(text: str, merge_blank: bool = True) -> str:
    """输出合并:去掉首尾空白、合并 3+ 连续换行为两段分隔;merge_blank=False 时原样返回"""
    if not text:
        return text
    out = text.strip()
    if merge_blank:
        out = re.sub(r"\n{3,}", "\n\n", out)
    return out


class ReplyEnhancePlugin(Plugin):
    """回复增强:输入累积 + 输出合并"""

    async def on_message_in(self, ctx):
        params = await self.get_params(ctx.object_id)
        if not params.get("accumulate"):
            return HookResult.CONTINUE
        # 累积:把本次用户消息加入缓冲
        redis = self.pctx.redis
        key = _BUFFER_KEY.format(oid=ctx.object_id)
        buf = await self._load(redis, key)
        buf.append({"text": ctx.user_text})
        await redis.set(key, json.dumps(buf, ensure_ascii=False))
        return HookResult.CONTINUE

    async def on_before_llm(self, ctx):
        params = await self.get_params(ctx.object_id)
        if not params.get("accumulate"):
            return HookResult.CONTINUE
        redis = self.pctx.redis
        key = _BUFFER_KEY.format(oid=ctx.object_id)
        buf = await self._load(redis, key)
        if not should_flush(buf, int(params.get("flush_count", 3))):
            # 未攒够:暂缓回复
            ctx.plugin_meta["held"] = True
            return HookResult.STOP
        # 攒够:合并缓冲为本次输入,清空缓冲,放行 LLM
        if buf:
            ctx.user_text = "\n".join(b.get("text", "") for b in buf)
            await redis.delete(key)
        return HookResult.CONTINUE

    async def on_message_out(self, ctx):
        params = await self.get_params(ctx.object_id)
        ctx.reply_text = merge_output(ctx.reply_text, bool(params.get("merge_blank_lines", True)))
        return HookResult.CONTINUE

    @staticmethod
    async def _load(redis, key) -> list[dict]:
        raw = await redis.get(key)
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
