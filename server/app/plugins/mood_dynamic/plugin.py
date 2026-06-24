"""
mood_dynamic 插件（人性化·动态心情）
维护心情值(0..1，0.5 中性，Redis 键 mychat:mood:{oid})：
- on_before_llm：把当前心情提示注入 system_prompt（影响回复语气）
- on_after_llm：按回复关键词情感更新心情（正向词↑/负向词↓）
- on_tick：心情向中性值衰减（久无互动趋于平静）
情感识别用关键词启发式(零依赖)，后续可换 LLM 情感分析。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 创建 mood_dynamic：心情模型 + 注入 + 情感更新 + 衰减
"""
from plugins.base import Plugin, HookResult

_MOOD_KEY = "mychat:mood:{oid}"
_POSITIVE = ["开心", "高兴", "喜欢", "好棒", "谢谢", "想你", "爱你", "哈哈", "嘿嘿", "😊", "😄", "❤"]
_NEGATIVE = ["难过", "伤心", "讨厌", "好烦", "好累", "不开心", "对不起", "想哭", "😢", "😡", "焦虑"]


class MoodDynamicPlugin(Plugin):
    """动态心情：心情值注入 + 情感更新 + 时间衰减"""

    async def on_before_llm(self, ctx):
        mood = await self._get(ctx.object_id)
        if ctx.system_prompt:
            ctx.system_prompt += f"\n[当前心情：{self._label(mood)}，让回复语气与之协调]"
        return HookResult.CONTINUE

    async def on_after_llm(self, ctx):
        params = await self.get_params(ctx.object_id)
        text = ctx.reply_text or ""
        step = float(params.get("step", 0.1))
        delta = 0.0
        if any(w in text for w in _POSITIVE):
            delta += step
        if any(w in text for w in _NEGATIVE):
            delta -= step
        if delta != 0.0:
            mood = await self._get(ctx.object_id)
            await self._set(ctx.object_id, max(0.0, min(1.0, mood + delta)))
        return HookResult.CONTINUE

    async def on_tick(self, ctx):
        params = await self.get_params(ctx.object_id)
        decay = float(params.get("decay", 0.05))
        neutral = float(params.get("neutral", 0.5))
        mood = await self._get(ctx.object_id)
        if mood > neutral:
            mood = max(neutral, mood - decay)
        elif mood < neutral:
            mood = min(neutral, mood + decay)
        await self._set(ctx.object_id, mood)
        return HookResult.CONTINUE

    async def _get(self, oid) -> float:
        v = await self.pctx.redis.get(_MOOD_KEY.format(oid=oid))
        try:
            return float(v) if v is not None else 0.5
        except (TypeError, ValueError):
            return 0.5

    async def _set(self, oid, mood: float) -> None:
        await self.pctx.redis.set(_MOOD_KEY.format(oid=oid), str(round(mood, 3)))

    @staticmethod
    def _label(mood: float) -> str:
        if mood >= 0.7:
            return "开心"
        if mood >= 0.55:
            return "愉悦"
        if mood >= 0.45:
            return "平静"
        if mood >= 0.3:
            return "低落"
        return "难过"
