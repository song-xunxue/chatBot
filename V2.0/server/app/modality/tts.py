"""
语音合成(TTS)Provider —— SiliconFlow CosyVoice2-0.5B(M-tts,2026-08-04)
文本 → mp3 音频 bytes。情感推导走 LLM(chat provider 复用),作 CosyVoice2 <|endofprompt|> 指令注入。

调用规格(https://api-docs.siliconflow.cn/docs/api/audio-speech-post):
  POST https://api.siliconflow.cn/v1/audio/speech
  header: Authorization: Bearer {key}
  body:   {model, input, voice(形如 Model:name), response_format, sample_rate, speed, gain}
  resp:   200 直接返回音频二进制

CosyVoice2 情感指令:input 形如 "{情感描述}<|endofprompt|>{实际文本}",
  支持自然语言情感/语气/方言描述 + 韵律标记([laughter]/[breath])。

音色(4 女声,面板下拉):anna 沉稳 / bella 激情 / claire 温柔 / diana 欢快。
产出 mp3 经 modality/silk.to_tencent_silk 转 silk 后发 QQ 语音条。

作者: 李文煜
日期: 2026-08-04
"""
import logging

import httpx

from core.config import settings
from llm.base import Message
from llm.resolver import resolve_provider
from modality.base import TTSProvider

logger = logging.getLogger(__name__)

# SiliconFlow OpenAI 兼容 base(与 llm/siliconflow.py 一致)
_BASE = "https://api.siliconflow.cn/v1"
_SYNTH_URL = f"{_BASE}/audio/speech"

# CosyVoice2-0.5B 预设女声(探测确认 20047 Invalid voice 的剔除;面板下拉用)
TTS_VOICES: dict[str, str] = {
    "anna": "沉稳女声",
    "bella": "激情女声",
    "claire": "温柔女声",
    "diana": "欢快女声",
}
DEFAULT_VOICE = "claire"  # 默认音色(配清浔温柔人设)


def _full_voice(voice: str, model: str) -> str:
    """音色名拼成 SiliconFlow 完整 voice 串(Model:name)。
    已带 model 前缀的原样返回;否则拼 model:voice。无效音色不在此纠错(API 会 400)。"""
    if not voice:
        voice = DEFAULT_VOICE
    return voice if ":" in voice else f"{model}:{voice}"


class SiliconFlowTTSProvider(TTSProvider):
    """SiliconFlow CosyVoice2 语音合成 provider。"""
    name = "siliconflow"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = api_key or settings.siliconflow_api_key
        self.model = model or settings.tts_model

    async def synthesize(self, text: str, voice: str, speed: float = 1.0,
                         gain: float = 0.0, emotion: str = "") -> bytes:
        """文本 → mp3 bytes。emotion 非空则前缀 <|endofprompt|> 作 CosyVoice2 情感指令。"""
        # CosyVoice2 情感指令:情感描述 + <|endofprompt|> + 实际文本(官方示例格式)
        inp = f"{emotion}<|endofprompt|>{text}" if emotion else text
        payload = {
            "model": self.model,
            "input": inp,
            "voice": _full_voice(voice, self.model),
            "response_format": "mp3",
            "sample_rate": 32000,   # mp3 支持 32000/44100;32000 够清晰且体积小
            "speed": speed,
            "gain": gain,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(_SYNTH_URL, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content


class StubTTSProvider(TTSProvider):
    """占位 TTS provider(未配 key 时降级):synthesize 返空 bytes,调用方据此跳过语音。"""
    name = "stub"

    async def synthesize(self, text: str, voice: str, speed: float = 1.0,
                         gain: float = 0.0, emotion: str = "") -> bytes:
        return b""


def get_tts(name: str = "") -> TTSProvider:
    """按名实例化 TTS provider;未配 key 或未知名 → stub(链路不断,语音被跳过)。
    优先显式 name,否则 settings.tts_provider,默认 siliconflow。"""
    n = (name or settings.tts_provider or "siliconflow").lower()
    if n == "siliconflow" and settings.siliconflow_api_key:
        return SiliconFlowTTSProvider()
    return StubTTSProvider()


async def infer_tts_emotion(text: str) -> str:
    """LLM 通读回复文本推导情感语气(供 CosyVoice2 <|endofprompt|> 指令)。

    走 resolve_provider("tts_emotion")(空配置回退 chat_provider);无可用 provider 或失败返空串
    (调用方据此纯文本合成,不发情感指令)。

    返回:简短情感词组(如"温柔撒娇"/"开心兴奋"/"平静"/"失落"),已清洗限长。
    """
    llm = resolve_provider("tts_emotion")
    if llm is None:
        return ""
    prompt = (
        "分析这句话的情感和语气,用简短词组描述供语音合成(如'温柔撒娇'/'开心兴奋'/'平静'/'失落'/'认真')。"
        "只输出描述词,不要解释,不要引号,10字以内。句子:" + text
    )
    try:
        resp = await llm.chat([Message(role="user", content=prompt)])
    except Exception as e:
        logger.warning("tts 情感推导失败,降级纯文本合成: %s", e)
        return ""
    desc = (resp.text or "").strip().strip("\"'""").strip()
    desc = desc.split("\n")[0].strip()  # 取首行
    if len(desc) > 20:
        desc = desc[:20]  # 限长,防 LLM 啰嗦污染指令
    return desc


async def resolve_voice(redis, oid: str, fallback: str) -> str:
    """当前音色解析:优先用 Redis 存的克隆 uri(mychat:tts:custom_voice:{oid},面板「设为当前」),
    未设置则回退 fallback(预设名 claire/anna/...)。克隆 uri 含冒号会被 _full_voice 原样透传。
    redis 可为 None(测试/降级),异常不阻塞→回退。"""
    if redis is not None:
        try:
            uri = await redis.get(f"mychat:tts:custom_voice:{oid}")
            if uri:
                return uri
        except Exception:
            logger.warning("resolve_voice 读克隆 uri 失败 oid=%s,回退预设", oid)
    return fallback


async def send_voice_reply(oid: str, text: str, *, msg_id: str, msg_seq: int,
                           voice: str, speed: float, gain: float,
                           emotion_enable: bool, send_text_also: bool,
                           human_authored: bool = False) -> dict | None:
    """共享:TTS 合成 + 转 silk + 上传 + 发语音(可选先文本)。插件 on_message_out 与 takeover _deliver 复用。

    成功返 {delivered:True, mode},失败/空产出返 None(调用方降级文本下发,不阻塞主流程)。
    msg_seq:起始序号——send_text_also 时 text 用 msg_seq、voice 用 msg_seq+1;否则 voice 用 msg_seq。
    human_authored:可选同发文本是否过出站守卫(代答 admin 文本 True 跳守卫;机器回复 False 过守卫)。
        语音本身是音频,无错误文本泄漏风险,send_c2c_voice 不过守卫。
    """
    import base64
    from modality.silk import to_tencent_silk
    from qq.api_client import (FILE_TYPE_VOICE, send_c2c_message,
                               send_c2c_voice, upload_c2c_file)
    try:
        emotion = await infer_tts_emotion(text) if emotion_enable else ""
        mp3 = await get_tts().synthesize(text, voice, speed, gain, emotion)
        if not mp3:
            logger.info("TTS 空产出(stub/无 key),跳过语音 oid=%s", oid)
            return None
        silk = await to_tencent_silk(mp3)
        up = await upload_c2c_file(oid, FILE_TYPE_VOICE, base64.b64encode(silk).decode())
        file_info = up.get("file_info")
        if not file_info:
            raise RuntimeError(f"上传未返 file_info: {up}")
        seq = msg_seq
        mode = "voice"
        if send_text_also:
            await send_c2c_message(oid, text, msg_id=msg_id, msg_seq=seq, human_authored=human_authored)
            seq += 1
            mode = "text+voice"
        await send_c2c_voice(oid, file_info, msg_id=msg_id, msg_seq=seq)
        logger.info("TTS 语音已发送 oid=%s voice=%s emotion=%s mode=%s",
                    oid, voice, emotion or "无", mode)
        return {"delivered": True, "mode": mode}
    except Exception:
        logger.exception("send_voice_reply 失败 oid=%s", oid)
        return None
