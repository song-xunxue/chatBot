"""
tts_reply 插件(回复转语音,M-tts 2026-08-04)
on_message_out(优先级 300,早于 continuous_send 400):回复文本 → SiliconFlow CosyVoice2 TTS
→ mp3 → silk → 上传 → 发 QQ 语音条。情感由 LLM 通读文本推导作 <|endofprompt|> 指令。

两开关语义(面板 config_schema 配):
  - 总开关 = 插件 enable(Plugin 页 n-switch;关=纯文本行为不变)
  - send_text_also:False(默认)=只发语音,设 ctx.reply_sent=True 让 webhook+continuous_send 跳过文本;
                  True = 先文本(msg_seq=1)再语音(msg_seq=2)
软失败:TTS 链路任一步异常 → 记日志,不设 reply_sent,webhook 发文本兜底(语音不可用不影响主流程)。

作者: 李文煜
日期: 2026-08-04

2026-08-04
变更说明：
  1. M-tts-3 新建 tts_reply 插件:on_message_out 整合 TTS+转码+上传+发语音,两开关语义
"""
import base64
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
        voice = params.get("voice") or "claire"
        speed = float(params.get("speed", 1.0))
        gain = float(params.get("gain", 0.0))
        emotion_enable = bool(params.get("emotion_enable", True))
        send_text_also = bool(params.get("send_text_also", False))
        try:
            from modality.tts import get_tts, infer_tts_emotion
            from modality.silk import to_tencent_silk
            from qq.api_client import (FILE_TYPE_VOICE, send_c2c_message,
                                       send_c2c_voice, upload_c2c_file)

            # 1. 情感推导:LLM 通读回复文本 → 情感词组(供 CosyVoice2 <|endofprompt|> 指令)
            emotion = await infer_tts_emotion(text) if emotion_enable else ""
            # 2. TTS 合成 → mp3 bytes
            mp3 = await get_tts().synthesize(text, voice, speed, gain, emotion)
            if not mp3:
                logger.info("TTS 空产出(stub/无 key),跳过语音 oid=%s", ctx.object_id)
                return HookResult.CONTINUE  # 无 key 降级,不阻塞,webhook 发文本
            # 3. mp3 → Tencent silk
            silk = await to_tencent_silk(mp3)
            # 4. 上传 silk → file_info(base64;srv_send_msg 默认 false 走被动回复)
            up = await upload_c2c_file(ctx.object_id, FILE_TYPE_VOICE,
                                       base64.b64encode(silk).decode())
            file_info = up.get("file_info")
            if not file_info:
                raise RuntimeError(f"上传未返 file_info: {up}")
            # 5. 发送:send_text_also 先文本(msg_seq=1)再语音(msg_seq=2);否则纯语音(msg_seq=1)
            seq = 1
            if send_text_also:
                await send_c2c_message(ctx.object_id, text, msg_id=msg_id, msg_seq=seq)
                seq = 2
            await send_c2c_voice(ctx.object_id, file_info, msg_id=msg_id, msg_seq=seq)
            ctx.reply_sent = True  # 标记已处理,webhook+continuous_send 跳过默认文本
            logger.info("TTS 语音已发送 oid=%s voice=%s emotion=%s text_also=%s",
                        ctx.object_id, voice, emotion or "无", send_text_also)
        except Exception:
            # 软失败:链路任一步失败 → 记日志,reply_sent 保持 False,webhook 发文本兜底
            logger.exception("TTS 语音发送失败,降级文本回复 oid=%s", ctx.object_id)
        return HookResult.CONTINUE
