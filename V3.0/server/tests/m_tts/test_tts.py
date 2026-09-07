"""
TTS provider 单测(M-tts,2026-08-04)
覆盖:4 女声表 + _full_voice 拼接 + get_tts 工厂(有/无 key 降级)+ SiliconFlow synthesize payload
(纯文本 vs 情感指令 <|endofprompt|> + speed/gain 透传)+ infer_tts_emotion(LLM 推导/无 provider/异常降级)。

作者: 李文煜
日期: 2026-08-04
"""
import httpx

from llm.base import LLMResponse
from modality import tts as tts_mod
from modality.tts import (
    DEFAULT_VOICE, TTS_VOICES, GPTSoVitsProvider, SiliconFlowTTSProvider, StubTTSProvider,
    _full_voice, get_tts, infer_tts_emotion,
)


def _patch_async_client(monkeypatch, handler):
    """patch httpx.AsyncClient 让 provider 内部 client 走 MockTransport。
    先捕获真实 AsyncClient 避免工厂内递归调到已 patch 的属性。"""
    real = httpx.AsyncClient

    def factory(**kw):
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _patch_sync_client(monkeypatch, handler):
    """patch httpx.Client(sync)让 GPTSoVitsProvider._sync_get/_sync_post 走 MockTransport。
    provider 改用同步 httpx + asyncio.to_thread(frp 异步不兼容修复)。"""
    real = httpx.Client

    def factory(**kw):
        return real(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(httpx, "Client", factory)


def test_voices_are_four_female():
    """仅 4 个女声(anna/bella/claire/diana),无男声"""
    assert set(TTS_VOICES.keys()) == {"anna", "bella", "claire", "diana"}
    assert DEFAULT_VOICE in TTS_VOICES


def test_full_voice_compose():
    """音色名拼成 Model:voice;已带前缀原样返回;空→默认"""
    m = "FunAudioLLM/CosyVoice2-0.5B"
    assert _full_voice("claire", m) == f"{m}:claire"
    assert _full_voice(f"{m}:anna", m) == f"{m}:anna"
    assert _full_voice("", m) == f"{m}:{DEFAULT_VOICE}"


def test_get_tts_stub_when_no_key(monkeypatch):
    """未配 siliconflow_api_key → stub(语音跳过,链路不断)"""
    monkeypatch.setattr(tts_mod.settings, "siliconflow_api_key", "")
    assert isinstance(get_tts("siliconflow"), StubTTSProvider)
    assert isinstance(get_tts(""), StubTTSProvider)


def test_get_tts_siliconflow_when_key(monkeypatch):
    """配了 key → SiliconFlowTTSProvider"""
    monkeypatch.setattr(tts_mod.settings, "siliconflow_api_key", "sk-fake")
    assert isinstance(get_tts("siliconflow"), SiliconFlowTTSProvider)


async def test_synthesize_payload_plain(monkeypatch):
    """纯文本合成:payload 含 model/voice(完整)/speed/gain,input 无指令"""
    captured = {}

    def handler(request):
        import json
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"FAKEMP3")

    _patch_async_client(monkeypatch, handler)
    p = SiliconFlowTTSProvider(api_key="sk-fake")
    out = await p.synthesize("你好", voice="claire", speed=1.2, gain=2.0)
    assert out == b"FAKEMP3"
    assert captured["auth"] == "Bearer sk-fake"
    assert captured["body"]["model"] == "FunAudioLLM/CosyVoice2-0.5B"
    assert captured["body"]["voice"].endswith(":claire")
    assert captured["body"]["input"] == "你好"  # 无 emotion → 无指令
    assert captured["body"]["speed"] == 1.2
    assert captured["body"]["gain"] == 2.0


async def test_synthesize_payload_emotion(monkeypatch):
    """情感指令:emotion 非空 → input = '{emotion}<|endofprompt|>{text}'"""
    captured = {}

    def handler(request):
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"X")

    _patch_async_client(monkeypatch, handler)
    p = SiliconFlowTTSProvider(api_key="sk-fake")
    await p.synthesize("夫君辛苦啦", voice="claire", emotion="温柔撒娇")
    assert captured["body"]["input"] == "温柔撒娇<|endofprompt|>夫君辛苦啦"


async def test_infer_tts_emotion_with_llm(monkeypatch):
    """有可用 LLM → 返回情感描述(取首行)"""
    captured = {}

    class FakeLLM:
        async def chat(self, messages, model="", **opts):
            captured["msgs"] = messages
            return LLMResponse(text="温柔、略带撒娇\n(不要这句)")

    monkeypatch.setattr(tts_mod, "resolve_provider", lambda task: FakeLLM())
    desc = await infer_tts_emotion("夫君辛苦啦")
    assert desc == "温柔、略带撒娇"
    assert captured["msgs"][0].role == "user"
    assert "夫君辛苦啦" in captured["msgs"][0].content


async def test_infer_tts_emotion_no_provider(monkeypatch):
    """无可用 LLM(resolve_provider 返 None)→ 返空串(纯文本合成)"""
    monkeypatch.setattr(tts_mod, "resolve_provider", lambda task: None)
    assert await infer_tts_emotion("任意文本") == ""


async def test_infer_tts_emotion_llm_error_fallback(monkeypatch):
    """LLM 调用抛异常 → 降级空串(不阻塞合成)"""
    class BoomLLM:
        async def chat(self, messages, model="", **opts):
            raise RuntimeError("LLM 挂了")

    monkeypatch.setattr(tts_mod, "resolve_provider", lambda task: BoomLLM())
    assert await infer_tts_emotion("文本") == ""


async def test_stub_returns_empty():
    """StubTTSProvider 返空 bytes(调用方据此跳过语音)"""
    assert await StubTTSProvider().synthesize("x", "claire") == b""


# —— GPT-SoVITS(GAG/api_v2)provider 测试,M-tts 2026-08-08 ——


def test_get_tts_gptsovits(monkeypatch):
    """tts_provider=gptsovits → 返 GPTSoVitsProvider"""
    monkeypatch.setattr(tts_mod.settings, "tts_provider", "gptsovits")
    assert isinstance(get_tts(""), GPTSoVitsProvider)


async def test_gptsovits_synthesize_payload(monkeypatch):
    """synthesize:_ensure_weights 跳过(已加载)+ POST /tts 透传 text/ref/prompt/speed,返 wav bytes"""
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        if request.method == "POST":
            captured["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, content=b"WAVBYTES")

    _patch_sync_client(monkeypatch, handler)
    # _loaded=模型 → _ensure_weights 跳过 set weights(只测 /tts 透传)
    monkeypatch.setattr(tts_mod, "_loaded_gpt_model", "mymodel")
    monkeypatch.setattr(tts_mod, "_loaded_sovits_model", "mysovits")
    p = GPTSoVitsProvider(api_base="http://x", gpt_model="mymodel", sovits_model="mysovits",
                          ref_audio="/ref.wav", prompt_text="参考文本")
    out = await p.synthesize("夫君辛苦啦", voice="ignored", speed=1.2)
    assert out == b"WAVBYTES"
    assert "/tts" in captured["url"]
    assert captured["body"]["text"] == "夫君辛苦啦"
    assert captured["body"]["ref_audio_path"] == "/ref.wav"
    assert captured["body"]["prompt_text"] == "参考文本"
    assert captured["body"]["speed_factor"] == 1.2
    assert captured["body"]["text_lang"] == "all_zh"
    # 2026-08-18 默认值对齐 GSV WebUI 面板(用户比对发现网页与面板合成不一致):
    # sample_steps=8(WebUI 默认,api 原默认 32)/top_k=15(面板默认)/fragment_interval=0.3(「句间停顿」滑条)
    assert captured["body"]["sample_steps"] == 8
    assert captured["body"]["top_k"] == 15
    assert captured["body"]["fragment_interval"] == 0.3
    assert captured["body"]["split_bucket"] is True
    # kwargs 覆盖默认(面板可调)
    out2 = await p.synthesize("再合成", voice="ignored", speed=1.0,
                              fragment_interval=0.15, sample_steps=16, top_k=30)
    assert out2 == b"WAVBYTES"
    assert captured["body"]["fragment_interval"] == 0.15
    assert captured["body"]["sample_steps"] == 16
    assert captured["body"]["top_k"] == 30


async def test_gptsovits_loads_weights_when_model_changes(monkeypatch):
    """_loaded=None → 首次合成调 set_gpt/sovits_weights;再次合成幂等跳过"""
    monkeypatch.setattr(tts_mod, "_loaded_gpt_model", None)
    monkeypatch.setattr(tts_mod, "_loaded_sovits_model", None)
    urls = []

    def handler(request):
        urls.append(str(request.url))
        if request.method == "POST":
            return httpx.Response(200, content=b"WAV")
        return httpx.Response(200)  # set weights GET

    _patch_sync_client(monkeypatch, handler)
    p = GPTSoVitsProvider(api_base="http://x", gpt_model="g.ckpt", sovits_model="s.pth",
                          ref_audio="/r.wav", prompt_text="x")
    await p.synthesize("hi", "v")
    assert any("set_gpt_weights" in u for u in urls)
    assert any("set_sovits_weights" in u for u in urls)
    # 第二次:_loaded 已设,幂等跳过 set
    urls.clear()
    await p.synthesize("hi2", "v")
    assert not any("set_gpt_weights" in u for u in urls)


async def test_gptsovits_no_ref_audio_raises(monkeypatch):
    """未配 ref_audio → synthesize 抛 RuntimeError(调用方软失败降级文本)"""
    monkeypatch.setattr(tts_mod.settings, "gptsovits_ref_audio", "")  # __init__ 回退 settings,须清空
    p = GPTSoVitsProvider(api_base="http://x", ref_audio="", prompt_text="")
    import pytest
    with pytest.raises(RuntimeError):
        await p.synthesize("x", "v")
