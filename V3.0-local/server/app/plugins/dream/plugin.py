"""
做梦与日记插件(dream)·on_tick 胶水
已过当日 dream_hour 后的首个 tick 触发一次 service.run_dream(对"昨天"做梦;
用 >= 判定,整点小时栈不可用时后续 tick 可补跑,不永久漏做)。
业务全在 plugins/dream/service.py,本文件只做三件事:参数判型(None 兜底)→ done 键门控
(should_dream:已过点 + 该目标日未做过)→ 尝试后置 done 键。全程软失败不外抛。
绝不发 QQ 消息:本插件与 service/storage 都不 import adapter/onebot/takeover 的 send_*。

done 键语义:无论 run_dream 成败,只要真正尝试过(过了 should_dream 门)就置位——
防止当天每分钟重试烧 LLM;键值=目标日串(YYYY-MM-DD),TTL 3 天自然过期。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新建:DreamPlugin,on_tick(priority=130) 委托 service.run_dream + done 键防重
  2. 审查修复:should_dream 由 now.hour==dream_hour 放宽为 >=,支持错过整点补跑

2026-11-01
变更说明:
  1. 日常日记定时触发:_maybe_journal——journal_hour(默认 22 点)后首个 tick 以她的
     第一人称总结当天聊天写一篇日常日记(service.run_journal,kind=journal),
     独立 done 键(mychat:journal:done:*)防重,与凌晨做梦互不影响;全程软失败不变
"""
import logging
from datetime import timedelta

from plugins.base import HookResult, Plugin
from plugins.dream import service

logger = logging.getLogger(__name__)

# done 键:oid+目标日 做过即置位(值=目标日串,TTL 3 天覆盖补跑窗口)
_DONE_KEY = "mychat:dream:done:{oid}:{yyyymmdd}"
_JOURNAL_DONE_KEY = "mychat:journal:done:{oid}:{yyyymmdd}"   # 2026-11-01 日常日记防重键
_DONE_TTL = 3 * 86400


class DreamPlugin(Plugin):
    """做梦与日记:on_tick 门控 + 委托 service.run_dream/run_journal(全程软失败)"""

    async def on_tick(self, ctx):
        try:
            await self._maybe_dream(ctx.object_id)
        except Exception:
            logger.exception("dream 处理异常 oid=%s(软失败,忽略本轮)", ctx.object_id)
        try:
            await self._maybe_journal(ctx.object_id)
        except Exception:
            logger.exception("journal 处理异常 oid=%s(软失败,忽略本轮)", ctx.object_id)
        return HookResult.CONTINUE

    async def _maybe_dream(self, oid: str) -> None:
        redis = self.pctx.redis
        # get_params 已合并 config_schema 默认值;面板可能存 null——每个参数取值都判 None 再转型
        params = await self.get_params(oid)
        hour = params.get("dream_hour")
        hour = service.DEFAULT_PARAMS["dream_hour"] if hour is None else int(hour)
        now = service._now()
        target = (now - timedelta(days=1)).date()   # 凌晨做梦写"昨天"的日记,目标日=前一天
        done_key = _DONE_KEY.format(oid=oid, yyyymmdd=target.strftime("%Y%m%d"))
        if not service.should_dream(now, hour, await redis.get(done_key)):
            return
        entry = await service.run_dream(redis, oid, target, params)
        # 置键放在尝试之后:无论成败只要真正尝试生成就置 done(run_dream 内部已捕获
        # LLM/解析异常返 None;此处还能抛的只剩 redis 异常,交给 on_tick 软失败)
        await redis.set(done_key, target.strftime("%Y-%m-%d"), ex=_DONE_TTL)
        if entry is None:
            logger.info("dream 本次未产出(无素材/LLM不可用/解析失败),今日不重试 oid=%s", oid)

    async def _maybe_journal(self, oid: str) -> None:
        """日常日记定时触发(2026-11-01):journal_hour(默认 22)后首个 tick 总结当天写日记。
        目标日=今天(区别于做梦的"昨天");独立 done 键防重,口径与 _maybe_dream 一致"""
        redis = self.pctx.redis
        params = await self.get_params(oid)
        hour = params.get("journal_hour")
        hour = service.DEFAULT_PARAMS["journal_hour"] if hour is None else int(hour)
        now = service._now()
        target = now.date()
        done_key = _JOURNAL_DONE_KEY.format(oid=oid, yyyymmdd=target.strftime("%Y%m%d"))
        if not service.should_journal(now, hour, await redis.get(done_key)):
            return
        entry = await service.run_journal(redis, oid, target, params)
        await redis.set(done_key, target.strftime("%Y-%m-%d"), ex=_DONE_TTL)
        if entry is None:
            logger.info("journal 本次未产出(无素材/LLM不可用/解析失败),今日不重试 oid=%s", oid)
