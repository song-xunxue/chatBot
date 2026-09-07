"""
代答 TTS 单测(M-tts-6,2026-08-04)
覆盖:_deliver TTS 分支(启用→语音且透传 msg_seq/human_authored;失败→降级文本;禁用→纯文本;
send_text_also 透传)+ _read_tts_voice_params(插件 config / 插件未加载默认)+ tts_config 端点。

作者: 李文煜
日期: 2026-08-04
"""
import pytest

import modality.tts as tts_mod
import plugins as plugins_mod
import storage.takeover_store as tstore
import takeover.service as svc

import adapter as adapter_mod
from tests.conftest import _RecordingAdapter


# —— _deliver TTS 分支 ——
def _patch(monkeypatch, *, tts_cfg, voice_result):
    """mock takeover_store.get_tts_config + _read_tts_voice_params + send_voice_reply + send_c2c_message"""
    async def fake_cfg(redis, oid):
        return tts_cfg
    monkeypatch.setattr(tstore, "get_tts_config", fake_cfg)

    async def fake_reader(oid):
        return ("claire", 1.0, 0.0, True)
    monkeypatch.setattr(svc, "_read_tts_voice_params", fake_reader)

    captured = {"voice": None, "text": []}

    async def fake_send_voice(oid, text, *, msg_id, msg_seq, voice, speed, gain,
                              emotion_enable, send_text_also, human_authored=False):
        captured["voice"] = dict(oid=oid, text=text, msg_id=msg_id, msg_seq=msg_seq,
                                 voice=voice, send_text_also=send_text_also, human_authored=human_authored)
        return voice_result
    monkeypatch.setattr(tts_mod, "send_voice_reply", fake_send_voice)

    # 文本出站走 fake_adapter(记录到 captured["text"],结构同原断言)
    class _CapAdapter(_RecordingAdapter):
        async def send_text(self, oid, content, *, msg_id="", msg_seq=1, human_authored=False):
            captured["text"].append(dict(oid=oid, content=content, msg_id=msg_id, msg_seq=msg_seq))
            return {"delivered": True, "mode": "fake_text"}
    monkeypatch.setattr(adapter_mod, "_current", _CapAdapter())
    return captured


async def test_deliver_tts_enabled_uses_voice(monkeypatch):
    """TTS 开启 + send_voice_reply 成功 → 返语音结果,透传 msg_seq/human_authored,不走文本"""
    cap = _patch(monkeypatch, tts_cfg={"enable": True, "send_text_also": False},
                 voice_result={"delivered": True, "mode": "voice"})
    r = await svc._deliver(None, "oid1", "代答内容", msg_id="MID", msg_seq=5, pid="p1")
    assert r == {"delivered": True, "mode": "voice"}
    assert cap["voice"]["msg_seq"] == 5            # 透传 msg_seq
    assert cap["voice"]["human_authored"] is True  # 代答 admin 文本不过守卫
    assert cap["voice"]["send_text_also"] is False
    assert cap["text"] == []                       # 未走文本下发


async def test_deliver_tts_send_text_also_passthrough(monkeypatch):
    """send_text_also 从 tts_cfg 透传到 send_voice_reply"""
    cap = _patch(monkeypatch, tts_cfg={"enable": True, "send_text_also": True},
                 voice_result={"delivered": True, "mode": "text+voice"})
    await svc._deliver(None, "oid1", "x", msg_id="MID", msg_seq=1, pid="p1")
    assert cap["voice"]["send_text_also"] is True


async def test_deliver_tts_fail_fallback_text(monkeypatch):
    """TTS 开启但 send_voice_reply 返 None(失败/空)→ 降级文本下发"""
    cap = _patch(monkeypatch, tts_cfg={"enable": True, "send_text_also": False},
                 voice_result=None)
    r = await svc._deliver(None, "oid1", "代答", msg_id="MID", msg_seq=1, pid="p1")
    assert r["delivered"] is True          # 文本被动下发成功
    assert cap["voice"] is not None        # TTS 尝试过
    assert len(cap["text"]) == 1           # 降级发了文本


async def test_deliver_tts_disabled_text_only(monkeypatch):
    """TTS 禁用 → 不调 send_voice_reply,纯文本下发(原行为)"""
    cap = _patch(monkeypatch, tts_cfg={}, voice_result={"delivered": True, "mode": "voice"})
    await svc._deliver(None, "oid1", "代答", msg_id="MID", msg_seq=1, pid="p1")
    assert cap["voice"] is None            # 未调 TTS
    assert len(cap["text"]) == 1           # 走文本


# —— _read_tts_voice_params(复用 tts_reply 插件 config)——
async def test_read_voice_params_from_plugin(monkeypatch):
    """tts_reply 插件已加载 → 读其 config 的 voice/speed/gain/emotion"""
    class FakeMgr:
        def list_loaded(self):
            return ["tts_reply"]

        async def get_params(self, name, oid):
            return {"voice": "anna", "speed": 1.5, "gain": 2.0, "emotion_enable": False}
    monkeypatch.setattr(plugins_mod, "get_plugin_manager", lambda: FakeMgr())
    assert await svc._read_tts_voice_params("oid1") == ("anna", 1.5, 2.0, False)


async def test_read_voice_params_defaults_no_plugin(monkeypatch):
    """插件未加载/manager None → 默认(claire/1.0/0.0/True)"""
    monkeypatch.setattr(plugins_mod, "get_plugin_manager", lambda: None)
    assert await svc._read_tts_voice_params("oid1") == ("claire", 1.0, 0.0, True)


# —— tts_config 端点 ——
async def test_endpoint_get_set_tts_config(monkeypatch):
    """GET 回显(未设全 False);PUT 调 set_tts_config 存。
    2026-08-18:REST 层 oid 校验须为 QQ 号(纯数字),测试 oid 用数字"""
    import api.rest_takeover as rt

    class FakeRedis:
        stored = None

        async def get(self, key):
            return FakeRedis.stored

        async def set(self, key, val):
            FakeRedis.stored = val

    fake = FakeRedis()
    monkeypatch.setattr(rt, "get_redis", lambda: _async_return(fake))

    got = await rt.get_tts_config("10001")
    assert got == {"object_id": "10001", "enable": False, "send_text_also": False}
    await rt.set_tts_config("10001", body={"enable": True, "send_text_also": False})
    got2 = await rt.get_tts_config("10001")
    assert got2 == {"object_id": "10001", "enable": True, "send_text_also": False}


async def _async_return(val):
    return val
