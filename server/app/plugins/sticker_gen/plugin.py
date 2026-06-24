"""
sticker_gen 插件（F-P-03 表情包生成）
on_after_llm：按回复内容派生 prompt 生成表情包图，加入 ctx.rich.sticker。
经 modality ImageProvider 接入(默认 stub)。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 创建 sticker_gen：调 ImageProvider 生成 + 富内容收集
"""
from plugins.base import Plugin, HookResult
from modality import get_image


class StickerGenPlugin(Plugin):
    """表情包生成：回复内容 → ctx.rich.sticker"""

    async def on_after_llm(self, ctx):
        text = (ctx.reply_text or "")[:120]
        if not text:
            return HookResult.CONTINUE
        params = await self.get_params(ctx.object_id)
        provider_name = str(params.get("provider", "stub"))
        prompt = f"表情包风格插画：{text}"
        artifact = await get_image(provider_name).generate(prompt)
        ctx.rich.setdefault("sticker", []).append({
            "url": artifact.url, "path": artifact.path,
            "format": artifact.format, "provider": artifact.provider,
        })
        return HookResult.CONTINUE
