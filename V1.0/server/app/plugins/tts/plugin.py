"""
tts 插件（F-P-01 语音合成）
on_after_llm：把回复文本合成为语音(空或超 max_chars 跳过)，加入 ctx.rich.audio。
真实语音服务经 modality provider 接入(默认 stub)，Q-10 确认后换真实 provider。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.3 创建 tts：调 TTSProvider 合成 + 富内容收集
"""
from plugins.base import Plugin, HookResult
from modality import get_tts


class TTSPlugin(Plugin):
    """语音合成：回复文本 → ctx.rich.audio"""

    async def on_after_llm(self, ctx):
        text = ctx.reply_text or ""
        params = await self.get_params(ctx.object_id)
        max_chars = int(params.get("max_chars", 500))
        if not text or len(text) > max_chars:
            return HookResult.CONTINUE                       # 空/过长不合成
        provider_name = str(params.get("provider", "stub"))
        voice = str(params.get("voice", "female-soft"))
        artifact = await get_tts(provider_name).synthesize(text, voice=voice)
        ctx.rich.setdefault("audio", []).append({
            "url": artifact.url, "path": artifact.path,
            "format": artifact.format, "provider": artifact.provider, "voice": voice,
        })
        return HookResult.CONTINUE
