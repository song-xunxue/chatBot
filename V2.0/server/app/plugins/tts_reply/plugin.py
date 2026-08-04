"""
tts_reply 插件(回复转语音,M-tts 2026-08-04)
on_message_out(优先级 300,早于 continuous_send 400):回复文本 → send_voice_reply 共享助手
(合成+转码+上传+发语音)。情感由 LLM 通读文本推导作 <|endofprompt|> 指令。

两开关语义(面板 config_schema 配):
  - 总开关 = 插件 enable(Plugin 页 n-switch;关=纯文本行为不变)
  - send_text_also:False(默认)=只发语音,设 ctx.reply_sent=True 让 webhook+continuous_send 跳过文本;
                  True = 先文本(msg_seq=1)再语音(msg_seq=2)
软失败:send_voice_reply 返 None → reply_sent 保持 False,webhook 发文本兜底。

作者: 李文煜
日期: 2026-08-04

2026-08-04
变更说明：
  1. M-tts-3 新建 tts_reply 插件:on_message_out 整合 TTS+转码+上传+发语音,两开关语义
  2. M-tts-6 重构:链路抽到 modality.tts.send_voice_reply 共享助手(插件+takeover 复用),本插件仅读 config 调用
"""
import logging

from plugins.base import Plugin, HookResult

logger = logging.getLogger(__name__)


class TTSReplyPlugin(Plugin):
    """回复转语音发送。config_schema 参数(voice/speed/gain/emotion_enable/send_text_also)面板可配。"""

    async def on_message_out(self, ctx):
        params = await self.get_params(ctx.object_id)
        msg_id = getattr(ctx, "qq_msg_id", "")
        text = ctx.reply_text or ""
        if not text or not msg_id:
            return HookResult.CONTINUE  # 无回复内容 或 非被动回复(无 msg_id),不处理
        from modality.tts import resolve_voice, send_voice_reply
        # 当前音色:优先克隆 uri(面板「设为当前」),回退 config 预设
        voice = await resolve_voice(self.pctx.redis, ctx.object_id, params.get("voice") or "claire")
        # 机器回复过守卫(human_authored=False);msg_seq 从 1 起(voice-only 用 1,text+voice 用 1/2)
        r = await send_voice_reply(
            ctx.object_id, text, msg_id=msg_id, msg_seq=1,
            voice=voice,
            speed=float(params.get("speed", 1.0)),
            gain=float(params.get("gain", 0.0)),
            emotion_enable=bool(params.get("emotion_enable", True)),
            send_text_also=bool(params.get("send_text_also", False)),
            human_authored=False,
        )
        if r and r.get("delivered"):
            ctx.reply_sent = True  # 标记已处理,webhook+continuous_send 跳过默认文本
        # 失败(None):reply_sent 保持 False,webhook 发文本兜底
        return HookResult.CONTINUE
