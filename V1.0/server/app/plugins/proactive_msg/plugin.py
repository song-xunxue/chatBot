"""
proactive_msg 插件（人性化·自主发消息）
on_tick：按概率(probability)与冷却(cooldown_sec)决定是否主动给对象发消息；
触发时经 ConnectionRegistry 广播 proactive_msg 信封(含 nudge 桌宠抖动)。
内容从 time_aware 缓存的时辰派生问候(无则用模板)。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 创建 proactive_msg：概率+冷却触发 + 广播+nudge
"""
import random
import time

from plugins.base import Plugin, HookResult

_LAST_KEY = "mychat:proactive:last:{oid}"
_GREETINGS = {
    "清晨": "早安呀，新的一天开始啦~",
    "上午": "在忙吗？记得喝水哦",
    "中午": "午饭吃了吗？",
    "下午": "下午茶时间到啦，歇一会儿吧",
    "晚上": "晚上好，今天过得怎么样？",
    "深夜": "还不睡吗？早点休息呀",
}


class ProactiveMsgPlugin(Plugin):
    """自主发消息：概率 + 冷却触发，广播问候 + nudge"""

    async def on_tick(self, ctx):
        params = await self.get_params(ctx.object_id)
        # 概率门：每次 tick 以 probability 的概率考虑发送
        if random.random() > float(params.get("probability", 0.2)):
            return HookResult.CONTINUE
        redis = self.pctx.redis
        now = time.time()
        cooldown = float(params.get("cooldown_sec", 3600))
        last = await redis.get(_LAST_KEY.format(oid=ctx.object_id))
        if last is not None and (now - float(last)) < cooldown:
            return HookResult.CONTINUE                      # 冷却内不重复打扰
        await redis.set(_LAST_KEY.format(oid=ctx.object_id), str(now))
        text = await self._greeting(ctx.object_id)
        await self._broadcast(ctx.object_id, text)
        return HookResult.CONTINUE

    async def _greeting(self, oid) -> str:
        """优先用 time_aware 缓存的时辰标签派生问候，无则用默认模板。
        注：直接读 mychat:timelabel:{oid}（由 time_aware on_tick 写入）；该键名与 time_aware 耦合，
        若 time_aware 未启用/键名变更，优雅回退默认模板（不影响主动推送主流程）。"""
        label = await self.pctx.redis.get(f"mychat:timelabel:{oid}")
        if label and label in _GREETINGS:
            return _GREETINGS[label]
        return "在吗？突然想到你~"

    async def _broadcast(self, oid, text):
        from plugins.connections import get_connection_registry
        from shared.protocol import envelope, now_ts
        msg = envelope("proactive_msg", {"text": text, "nudge": True},
                       object_id=oid, ts=now_ts())
        await get_connection_registry().broadcast(oid, msg)
