"""
time_aware 插件(人性化·时间观念)
- on_before_llm:把当前时辰/季节提示注入 system_prompt(让回复带时间感)
- on_tick:把当前时辰标签缓存到 Redis(供主动聊天模块决定是否问候)
时辰/季节判定为纯函数。

M6 从 V1.0 收敛到 V2.0(代码零改;Plugin 基类/EventBus/redis 一致)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M6 从 V1.0 收敛 time_aware 到 V2.0(零改;on_before_llm 注入时间上下文,on_tick 缓存标签)
"""
from datetime import datetime

from plugins.base import Plugin, HookResult

_TIME_KEY = "mychat:timelabel:{oid}"


def time_of_day(hour: int) -> str:
    """按时辰返回标签(纯函数,0-23)"""
    if 5 <= hour < 9:
        return "清晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 23:
        return "晚上"
    return "深夜"


def season_label(month: int) -> str:
    """按月份返回季节(纯函数,1-12)"""
    if month in (3, 4, 5):
        return "春"
    if month in (6, 7, 8):
        return "夏"
    if month in (9, 10, 11):
        return "秋"
    return "冬"


class TimeAwarePlugin(Plugin):
    """时间观念:注入时间上下文 + 缓存时辰标签"""

    async def on_before_llm(self, ctx):
        now = datetime.now()
        label = f"{season_label(now.month)}季·{time_of_day(now.hour)}"
        if ctx.system_prompt:
            ctx.system_prompt += f"\n[当前时间:{label}]"
        return HookResult.CONTINUE

    async def on_tick(self, ctx):
        now = datetime.now()
        await self.pctx.redis.set(_TIME_KEY.format(oid=ctx.object_id), time_of_day(now.hour))
        return HookResult.CONTINUE

    async def current_label(self, oid: str) -> str:
        """取缓存的时辰标签(供主动聊天模块读取)"""
        v = await self.pctx.redis.get(_TIME_KEY.format(oid=oid))
        return v or ""
