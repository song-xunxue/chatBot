"""
image_gen 插件（F-P-02 图像生成）
on_after_llm：在每日配额内时，按回复文本派生 prompt 调 ImageProvider 生成图，加入 ctx.rich.image；
超额时把回复改为"自主拒绝"并 STOP 图像分支（跳过后续回复增强），不生成。
配额键 mychat:quota:{oid}:img:{date}（按日计数，跨日自动换键）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 创建 image_gen：日配额(INCR/GET) + provider 生成 + 超额拒绝
  2. M4.3-review 修正：原子占用配额(用 INCR 返回值判定，消除 GET/INCR TOCTOU) + 首次设 48h TTL(防日键堆积)
     + provider 失败回滚 DECR(不泄漏配额) + 超额拒绝时清理已收集富内容(防文本/音频错配)
"""
from datetime import date

from plugins.base import Plugin, HookResult
from modality import get_image

_QUOTA_KEY = "mychat:quota:{oid}:img:{d}"


class ImageGenPlugin(Plugin):
    """图像生成 + 每日配额"""

    async def on_after_llm(self, ctx):
        params = await self.get_params(ctx.object_id)
        quota = int(params.get("daily_quota", 5))
        redis = self.pctx.redis
        key = _QUOTA_KEY.format(oid=ctx.object_id, d=date.today().isoformat())
        # 原子占用配额：用 INCR 返回值判定（消除 GET/INCR 之间的 TOCTOU 竞态）
        cnt = await redis.incr(key)
        if cnt == 1:
            await redis.expire(key, 172800)              # 首次设 48h TTL，防日键无限堆积
        if cnt > quota:
            await redis.decr(key)                         # 超额回滚，不消耗配额
            ctx.reply_text = "（今天画太多啦，先歇一会儿～）"
            ctx.plugin_meta["image_refused"] = True
            ctx.rich.pop("audio", None)                   # 拒绝语替换原回复：清理本回合已收集富内容，防文本/音频错配
            ctx.rich.pop("sticker", None)
            return HookResult.STOP
        # 配额内：生成图像；provider 失败则回滚配额
        provider_name = str(params.get("provider", "stub"))
        prompt = self._build_prompt(ctx)
        try:
            artifact = await get_image(provider_name).generate(prompt)
        except Exception:
            await redis.decr(key)                         # 生成失败回滚配额
            raise
        ctx.rich.setdefault("image", []).append({
            "url": artifact.url, "path": artifact.path,
            "format": artifact.format, "provider": artifact.provider,
        })
        return HookResult.CONTINUE

    @staticmethod
    def _build_prompt(ctx) -> str:
        """派生图像 prompt：优先用回复文本，截断长度"""
        text = (ctx.reply_text or ctx.user_text or "")[:200]
        return f"为以下内容配图：{text}" if text else "温馨日常插画"
