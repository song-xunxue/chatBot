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
产出音频(mp3/wav)直发 adapter.send_voice,由 NapCat 内置 ffmpeg 自转 silk(2026-10-01,
勿再走 modality/silk 自编——NapCat 对自编 silk 时长解析为 0,QQ 只显 1s 截断)。

日期: 2026-08-04

2026-10-01
变更说明：
    1. 修语音 1s 截断:send_voice_reply 去掉 to_tencent_silk,合成音频直传
       (线上对照实验:NapCat 自转 12.7s 完整,自编 silk 0s)。silk.py 模块保留不再被调用。
"""
import asyncio
import json
import logging
import time

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
DEFAULT_VOICE = "claire"  # 默认音色(配温柔人设)


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


# —— GPT-SoVITS(GAG/api_v2 本地服务)provider,M-tts 2026-08-08 主力 TTS ——
# 服务端已加载的模型(幂等:换模型才重新 set weights,避免每次合成重复加载)
_loaded_gpt_model: str | None = None
_loaded_sovits_model: str | None = None


class GPTSoVitsProvider(TTSProvider):
    """GPT-SoVITS(本地 GAG 启动的 api_v2 服务)TTS provider。
    音色由 gpt_model + sovits_model + ref_audio_path + prompt_text 决定(config 配置,首版固定单音色)。
    voice/emotion 参数本版忽略(GPT-SoVITS 无音色名/情感指令;多情感档位后续扩多条参考音频)。
    合成返 wav bytes,直发 adapter.send_voice(NapCat 自转 silk)。"""
    name = "gptsovits"

    def __init__(self, api_base: str = "", gpt_model: str = "", sovits_model: str = "",
                 ref_audio: str = "", prompt_text: str = ""):
        self.api_base = (api_base or settings.gptsovits_api_base).rstrip("/")
        self.gpt_model = gpt_model or settings.gptsovits_gpt_model
        self.sovits_model = sovits_model or settings.gptsovits_sovits_model
        self.ref_audio = ref_audio or settings.gptsovits_ref_audio
        self.prompt_text = prompt_text or settings.gptsovits_prompt_text

    # frp 隧道对异步 httpx(httpcore)不兼容(Server disconnected),改用同步 httpx + asyncio.to_thread
    def _sync_get(self, endpoint, params=None):
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{self.api_base}/{endpoint}", params=params or {})
            r.raise_for_status()
            return r

    def _sync_post(self, endpoint, payload):
        with httpx.Client(timeout=120.0) as c:
            r = c.post(f"{self.api_base}/{endpoint}", json=payload)
            r.raise_for_status()
            return r.content

    async def _ensure_weights(self) -> None:
        """确保服务端加载了配置的模型(幂等,换模型才重新 set)。GAG 启动器或 GUI 可能已加载。"""
        global _loaded_gpt_model, _loaded_sovits_model
        if self.gpt_model and _loaded_gpt_model != self.gpt_model:
            await asyncio.to_thread(self._sync_get, "set_gpt_weights", {"weights_path": self.gpt_model})
            _loaded_gpt_model = self.gpt_model
        if self.sovits_model and _loaded_sovits_model != self.sovits_model:
            await asyncio.to_thread(self._sync_get, "set_sovits_weights", {"weights_path": self.sovits_model})
            _loaded_sovits_model = self.sovits_model

    async def synthesize(self, text: str, voice: str, speed: float = 1.0,
                         gain: float = 0.0, emotion: str = "", **kwargs) -> bytes:
        if not self.ref_audio:
            raise RuntimeError("GPT-SoVITS 未配 ref_audio_path(参考音频,必填)")
        await self._ensure_weights()
        # 合成参数:面板可配的走 kwargs(透传),不可配的固定;voice/emotion 忽略(GPT-SoVITS 音色=参考音频)
        # 默认值对齐 GSV WebUI 面板(2026-08-18 用户比对发现网页与 GSV 面板合成不一致):
        #   api_v2 默认 sample_steps=32 但 WebUI 默认 8(扩散步数直接改变音频生成);
        #   top_k api 默认 15(原我们写 5);fragment_interval 即 WebUI「句间停顿秒数」滑条(每段尾补静音)
        payload = {
            "text": text, "text_lang": "all_zh",
            "ref_audio_path": self.ref_audio,
            "prompt_text": self.prompt_text, "prompt_lang": "all_zh",
            "top_k": kwargs.get('top_k', 15),
            "top_p": kwargs.get('top_p', 1.0),
            "temperature": kwargs.get('temperature', 1.0),
            "text_split_method": "cut1",
            "batch_size": kwargs.get('batch_size', 4),
            "batch_threshold": 0.75,
            "fragment_interval": kwargs.get('fragment_interval', 0.3),
            "split_bucket": True, "return_fragment": False,
            "speed_factor": speed, "streaming_mode": False, "seed": -1,
            "parallel_infer": True,
            "repetition_penalty": kwargs.get('repetition_penalty', 1.35),
            "sample_steps": kwargs.get('sample_steps', 8),
            "media_type": "wav",
        }
        return await asyncio.to_thread(self._sync_post, "tts", payload)


# —— BreezeBlue 云端 TTS(2026-11-03 用户接入)——
# 文档:https://docs.breezeblue.ai/api-reference/text-to-speech/convert-text-to-speech
# POST {api_base}/text-to-speech/{voice_id}?output_format=mp3,header xi-api-key,返回 mp3 二进制。
# 音色在 BreezeBlue 控制台设计保存(Voice ID),本端 voice 参数忽略(同 GPTSoVits 口径)。
# 护栏(控费):单次文本截断 breezeblue_max_chars + 每日次数 breezeblue_daily_limit(redis 计数)。
# 费用口径(官方博客 2026-10-29):中文每字 2 计费字符,1 credit=10 字符,$3/10000 credits;
#   Free 套餐每天可领 400 credits≈40 条 50 字回复。失败抛异常,send_voice_reply 捕获回退文本。


def _append_wav_silence(data: bytes, sec: float) -> bytes:
    """wav 尾部追加静音帧(2026-11-08 结尾余韵:用户反馈 B 版"结尾太快很突然")。
    PCM 补静音=纯字节操作(wave 标准库,零依赖):读参数 → 原帧+静音帧 → 重写。
    8bit 静音=0x80(无符号中点),其余位深=0x00;解析失败(非 PCM wav)原样返回不炸。"""
    import io as _io
    import wave as _wave
    try:
        src = _wave.open(_io.BytesIO(data), "rb")
        params = src.getparams()
        frames = src.readframes(src.getnframes())
        src.close()
        nch, width, rate = params.nchannels, params.sampwidth, params.framerate
        silence = (b"\x80" if width == 1 else b"\x00") * int(rate * sec) * nch * width
        buf = _io.BytesIO()
        out = _wave.open(buf, "wb")
        out.setnchannels(nch)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(frames + silence)
        out.close()
        return buf.getvalue()
    except Exception:
        logger.warning("wav 尾静音追加失败(原样返回): %.100s", data[:40])
        return data


class BreezeBlueTTSProvider(TTSProvider):
    """BreezeBlue 云端 TTS provider(用户 2026-11-03 接入,音色 voc_b86bfwct4cjn=6390 栈专属)。"""
    name = "breezeblue"

    def __init__(self, api_key: str = "", voice_id: str = "", api_base: str = "",
                 max_chars: int = 0, daily_limit: int = 0):
        self.api_key = api_key or settings.breezeblue_api_key
        self.voice_id = voice_id or settings.breezeblue_voice_id
        self.api_base = (api_base or settings.breezeblue_api_base).rstrip("/")
        self.max_chars = max_chars or settings.breezeblue_max_chars
        self.daily_limit = daily_limit or settings.breezeblue_daily_limit

    async def _guard_daily(self) -> None:
        """每日次数护栏(redis INCR 按日计数,TTL 2 天自然清);超限抛 RuntimeError
        (send_voice_reply 捕获回退文本)。redis 不可用时 cnt=None 护栏放行
        (语音非关键路径,降级已有);注意超限判定在 try 外——redis 故障的异常
        不得与「超限」共用异常通道(首版 except RuntimeError 混吞过)。"""
        cnt = None
        try:
            from storage.redis_client import get_redis
            redis = await get_redis()
            day = time.strftime("%Y%m%d")
            key = f"mychat:tts:breezeblue:count:{day}"
            cnt = await redis.incr(key)
            await redis.expire(key, 2 * 86400)
        except Exception:
            logger.warning("BreezeBlue 每日护栏计数失败(放行,不影响合成)", exc_info=True)
        if cnt is not None and cnt > self.daily_limit:
            raise RuntimeError(f"BreezeBlue 每日用量上限({self.daily_limit})已满,今日回退文字")

    async def synthesize(self, text: str, voice: str = "", speed: float = 1.0,
                         gain: float = 0.0, emotion: str = "", **kwargs) -> bytes:
        if not self.api_key or not self.voice_id:
            raise RuntimeError("BreezeBlue 未配 api_key/voice_id(.env BREEZEBLUE_API_KEY/BREEZEBLUE_VOICE_ID)")
        text = (text or "").strip()
        if not text:
            return b""
        if len(text) > self.max_chars:
            text = text[:self.max_chars]   # 截断控费(长回复保留文字的口径由调用方决定)
        await self._guard_daily()
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        # 2026-11-08 情感表演(用户反馈"太平淡"):emotion 参数对本 provider 语义=完整表演指令
        # (infer_tts_instruction 生成,官方 voice-instruction-prompting 口径);
        # voice_settings.guidance_scale=3(表现力档上限;2026-11-08 用户反馈 2 太收致平淡,官方范围 1-10)
        # speed 原生支持(0.5-2.0 变速不变调;2026-11-08 用户要求 1.1 倍)——send_voice_reply 透传
        payload = {"text": text}
        if emotion:
            payload["instructions"] = emotion
        vs: dict = {"guidance_scale": 3}
        if speed and speed != 1.0:
            vs["speed"] = max(0.5, min(2.0, float(speed)))
        payload["voice_settings"] = vs
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.api_base}/text-to-speech/{self.voice_id}",
                headers=headers, json=payload, params={"output_format": "wav"})
            resp.raise_for_status()
            audio = resp.content
        # 2026-11-08 结尾余韵(用户反馈"结尾太快很突然"):wav 尾部补静音帧。
        # 走 wav 而非 mp3 的原因:wav 是 PCM,尾部补静音=纯字节操作(wave 标准库),零依赖。
        tail = float(settings.breezeblue_tail_silence)
        if tail > 0:
            audio = _append_wav_silence(audio, tail)
        return audio


# —— GPT-SoVITS 就绪状态检测(M-tts-2,2026-08-10:心跳缓存优先 + 懒探测,免重复打 frp 隧道)——
# 心跳:本地启动器 api_v2 就绪后每 30s POST /tts/gptsovits/heartbeat 上报,服务端写 Redis TTL 90s。
# status 查询:心跳未过期直接返不探测;过期/无心跳且 probe=True 才主动探测根路径。
HEARTBEAT_KEY = "mychat:tts:gptsovits:heartbeat"
HEARTBEAT_TTL = 90  # 秒;启动器每 30s 续期,90s=3 周期容错(崩溃后最多 90s 状态过期)


def _sync_probe(api_base: str, timeout: float = 4.0):
    """同步探测 api_v2 根路径。任何 HTTP 响应(含 404)= TCP/HTTP 通 = 服务在线;
    连接拒绝/超时 = 离线。同步 httpx + asyncio.to_thread 包装(避 frp 隧道异步不兼容坑,与 GPTSoVitsProvider 同款)。
    GPT-SoVITS api_v2 启动先加载完模型再开服务,故"响应"即"模型就绪"。返 (reachable, latency_ms, detail)。"""
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as c:                   # 同步 client(可被测试 _patch_sync_client mock)
            r = c.get(f"{api_base.rstrip('/')}/")                   # 根路径探测(不依赖具体路由,404 也算在线)
        return True, int((time.perf_counter() - t0) * 1000), f"HTTP {r.status_code}"
    except httpx.ConnectTimeout:
        return False, -1, "连接超时(api_v2 未启动或 frp 隧道断)"
    except httpx.ConnectError:
        return False, -1, "连接被拒(api_v2 加载中或未启动)"
    except Exception as e:
        return False, -1, f"探测失败: {type(e).__name__}"


async def check_gptsovits_status(redis=None, *, force: bool = False, probe: bool = True) -> dict:
    """聚合 GPT-SoVITS 就绪状态。心跳缓存优先(命中不打 frp);否则按 probe 决定是否探测。

    force:True 跳过心跳直接探测(前端「重新检测」按钮)。
    probe:心跳未命中时是否主动探测;False 只读心跳(折叠态/轮询:绝不打 frp)。
    返 {tts_provider, api_base, source('heartbeat'/'probe'/'none'), reachable, latency_ms,
        config_ok, missing, detail, heartbeat_ts}。"""
    api_base = settings.gptsovits_api_base
    res = {
        "tts_provider": settings.tts_provider, "api_base": api_base,
        "source": "none", "reachable": False, "latency_ms": -1,
        "config_ok": False, "missing": [], "detail": "", "heartbeat_ts": None,
    }
    # config 完整性(ref_audio 必填——synthesize 空会 raise;gpt/sovits 通常 tts_infer.yaml 预配但建议显式)
    missing = [k for k, v in (
        ("ref_audio", settings.gptsovits_ref_audio),
        ("gpt_model", settings.gptsovits_gpt_model),
        ("sovits_model", settings.gptsovits_sovits_model),
    ) if not v]
    res["missing"] = missing
    res["config_ok"] = not missing

    # 非 gptsovits provider:不探测(本地模型概念不适用,前端据此灰显)
    if (settings.tts_provider or "").lower() != "gptsovits":
        res["detail"] = f"当前 TTS provider={settings.tts_provider}（非本地 GPT-SoVITS）"
        return res

    # 心跳优先(force 时跳过;命中即返,不打 frp)
    if not force and redis is not None:
        try:
            raw = await redis.get(HEARTBEAT_KEY)
            if raw:
                hb = json.loads(raw)
                res.update(source="heartbeat", reachable=True,
                           latency_ms=hb.get("latency_ms", -1),
                           detail="本地启动器已上报就绪", heartbeat_ts=hb.get("ts"))
                return res
        except Exception:
            logger.warning("读 GPT-SoVITS 心跳缓存失败,降级探测", exc_info=True)

    # 心跳未命中 + probe=False → 不探测(折叠态/轮询:零 frp 开销)
    if not probe:
        res["detail"] = "未检测（展开或点重新检测）"
        return res

    # 主动探测(force 或 probe=True 且心跳未命中)
    reachable, lat, detail = await asyncio.to_thread(_sync_probe, api_base)
    res.update(source="probe", reachable=reachable, latency_ms=lat,
               detail=detail if reachable else f"未连接：{detail}")
    return res


def get_tts(name: str = "") -> TTSProvider:
    """按名实例化 TTS provider;未知名 → settings.tts_provider,默认 siliconflow。
    siliconflow 无 key / gptsovits 未配 → 降级 stub(链路不断,语音跳过,文本兜底)。
    breezeblue(2026-11-03):无 key/voice_id → 同样降级 stub。"""
    n = (name or settings.tts_provider or "siliconflow").lower()
    if n == "gptsovits":
        return GPTSoVitsProvider()
    if n == "breezeblue":
        return BreezeBlueTTSProvider()
    if n == "siliconflow" and settings.siliconflow_api_key:
        return SiliconFlowTTSProvider()
    return StubTTSProvider()


async def infer_tts_instruction(text: str) -> str:
    """BreezeBlue 表演指令生成(2026-11-08 情感丰富化,官方 voice-instruction-prompting
    「用你自己的 LLM 写指令」工作流的中文化+恋人场景定制):
    LLM 通读台词,从 情境/意图/情感强度/节奏重音/身体状态 五维度挑 2-3 个,
    输出 1-2 句中文表演指令(如「轻快雀跃的语气,像刚想到什么好主意,尾音上扬」)。
    走 resolve_provider("tts_emotion");失败返空串(调用方降级无指令合成)。"""
    llm = resolve_provider("tts_emotion")
    if llm is None:
        return ""
    prompt = (
        "为下面的台词写一条简短的 TTS 表演指令(与台词同语言,中文)。\n"
        "场景:恋人之间的 QQ 语音消息;说话者是年轻女性角色,语气自然、像随手发的语音,"
        "不是播音腔。听者是她在意的恋人。\n"
        "从 情境/意图/情感强度/节奏重音/身体状态 里挑 2-3 个最有用的方向,用 1-2 句话写;"
        "记得提到结尾要轻放缓、带一点余韵再收,不要戛然而止;"
        "不要互相矛盾的指令,不要改变说话者身份,不要承诺具体时间点。只输出指令本身,不要解释。\n\n"
        f"台词:{text}"
    )
    try:
        resp = await llm.chat([Message(role="user", content=prompt)])
    except Exception as e:
        logger.warning("tts 表演指令生成失败,降级无指令合成: %s", e)
        return ""
    out = (resp.text or "").strip().strip("\"'“”").strip()
    if len(out) > 120:
        out = out[:120]   # 限长防 LLM 啰嗦
    return out


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
                           human_authored: bool = False, **tts_params) -> dict | None:
    """共享:TTS 合成 + 发语音(可选先文本)。插件 on_message_out 与 takeover _deliver 复用。

    成功返 {delivered:True, mode},失败/空产出返 None(调用方降级文本下发,不阻塞主流程)。
    音频不做本地转码直传(NapCat 内置 ffmpeg 自转 silk;自编 silk 其时长解析 0s,2026-10-01)。
    msg_seq:起始序号——send_text_also 时 text 用 msg_seq、voice 用 msg_seq+1;否则 voice 用 msg_seq。
    human_authored:可选同发文本是否过出站守卫(代答 admin 文本 True 跳守卫;机器回复 False 过守卫)。
        语音本身是音频,无错误文本泄漏风险,send_c2c_voice 不过守卫。
    """
    from adapter import get_current_adapter   # V3.0:平台适配器(onebot=record 段 base64)
    adapter = await get_current_adapter()
    try:
        tts = get_tts()
        if getattr(tts, "name", "") == "breezeblue":
            # 2026-11-08 修(用户反馈面板路径"有气无力"):BreezeBlue 的表演指令**无条件启用**——
            # 这是该 API 的正确用法,无指令=平淡朗读;emotion_enable 开关只管 CosyVoice 情感短词口径
            emotion = await infer_tts_instruction(text)
        else:
            emotion = await infer_tts_emotion(text) if emotion_enable else ""   # CosyVoice:短词 <|endofprompt|>
        audio = await tts.synthesize(text, voice, speed, gain, emotion, **tts_params)
        if not audio:
            logger.info("TTS 空产出(stub/无 key),跳过语音 oid=%s", oid)
            return None
        seq = msg_seq
        mode = "voice"
        if send_text_also:
            await adapter.send_text(oid, text, msg_id=msg_id, msg_seq=seq, human_authored=human_authored)
            seq += 1
            mode = "text+voice"
        await adapter.send_voice(oid, audio, msg_id=msg_id, msg_seq=seq)
        logger.info("TTS 语音已发送 oid=%s voice=%s emotion=%s mode=%s",
                    oid, voice, emotion or "无", mode)
        return {"delivered": True, "mode": mode}
    except Exception:
        logger.exception("send_voice_reply 失败 oid=%s", oid)
        return None
