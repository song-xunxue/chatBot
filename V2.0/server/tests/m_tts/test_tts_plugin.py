"""
tts_reply 插件 + 插件参数端点单测(M-tts,2026-08-04)
覆盖:on_message_out 端到端(情感→TTS→silk→上传→发语音,mock 各步)+ send_text_also 两分支
+ 情感开关 + 软失败(reply_sent 保持 False)+ 无 msg_id/stub 空产出 跳过 + 上传 base64_silk/file_type=3
+ REST params GET/PUT(get_plugin_params/set_plugin_params 薄包装)。

作者: 李文煜
日期: 2026-08-04
"""
import base64

import modality.silk as silk_mod
import modality.tts as tts_mod
import plugins.tts_reply.plugin as tts_plugin_mod
import qq.api_client as api
from plugins.base import PluginContext

DEFAULT_PARAMS = {"voice": "claire", "speed": 1.0, "gain": 0.0,
                  "emotion_enable": True, "send_text_also": False}


class _Ctx:
    """轻量 MessageContext(只含插件用到的字段)"""
    def __init__(self, oid="oid1", reply_text="夫君辛苦啦", qq_msg_id="MID"):
        self.object_id = oid
        self.reply_text = reply_text
        self.qq_msg_id = qq_msg_id
        self.reply_sent = False


class _FakeManager:
    def __init__(self, params):
        self._params = params

    async def get_params(self, name, oid):
        return dict(self._params)


class _FakeManifest:
    name = "tts_reply"


def _make_plugin(params):
    p = tts_plugin_mod.TTSReplyPlugin()
    p.manifest = _FakeManifest()
    p.pctx = PluginContext(manager=_FakeManager(params), redis=None, settings=None, manifest=p.manifest)
    return p


def _mock_chain(monkeypatch, *, mp3=b"MP3", silk=b"\x02SILK", file_info="FI-xxx", synth_exc=None):
    """mock 整条链(get_tts/infer/silk/upload/send_voice/send_msg),返回 captured"""
    captured = {"send_msg": [], "send_voice": [], "upload": []}

    class FakeProvider:
        async def synthesize(self, text, voice, speed, gain, emotion="", **kwargs):
            captured["synth"] = dict(text=text, voice=voice, speed=speed, gain=gain, emotion=emotion)
            if synth_exc:
                raise synth_exc
            return mp3

    monkeypatch.setattr(tts_mod, "get_tts", lambda: FakeProvider())

    async def fake_emotion(text):
        captured["emotion_text"] = text
        return "温柔撒娇"
    monkeypatch.setattr(tts_mod, "infer_tts_emotion", fake_emotion)

    async def fake_silk(audio, *, ffmpeg=""):
        captured["silk_in"] = audio
        return silk
    monkeypatch.setattr(silk_mod, "to_tencent_silk", fake_silk)

    async def fake_upload(oid, ft, data, *, srv_send_msg=False):
        captured["upload"].append(dict(oid=oid, ft=ft, data=data))
        return {"file_info": file_info}
    monkeypatch.setattr(api, "upload_c2c_file", fake_upload)

    async def fake_send_voice(oid, fi, *, msg_id="", msg_seq=1, content=""):
        captured["send_voice"].append(dict(oid=oid, fi=fi, msg_id=msg_id, msg_seq=msg_seq))
        return {"id": "V1"}
    monkeypatch.setattr(api, "send_c2c_voice", fake_send_voice)

    async def fake_send_msg(oid, content, *, msg_id="", msg_seq=1, human_authored=False):
        captured["send_msg"].append(dict(oid=oid, content=content, msg_id=msg_id, msg_seq=msg_seq))
        return {"id": "T1"}
    monkeypatch.setattr(api, "send_c2c_message", fake_send_msg)
    return captured


async def test_voice_only_sets_reply_sent(monkeypatch):
    """send_text_also=False:只发语音(msg_seq=1),reply_sent=True,无文本下发,情感指令注入"""
    cap = _mock_chain(monkeypatch)
    ctx = _Ctx()
    await _make_plugin(DEFAULT_PARAMS).on_message_out(ctx)
    assert ctx.reply_sent is True
    assert cap["send_voice"] == [dict(oid="oid1", fi="FI-xxx", msg_id="MID", msg_seq=1)]
    assert cap["send_msg"] == []
    assert cap["synth"]["emotion"] == "温柔撒娇"


async def test_text_also_sends_both(monkeypatch):
    """send_text_also=True:先文本(msg_seq=1)再语音(msg_seq=2)"""
    cap = _mock_chain(monkeypatch)
    ctx = _Ctx()
    await _make_plugin({**DEFAULT_PARAMS, "send_text_also": True}).on_message_out(ctx)
    assert ctx.reply_sent is True
    assert cap["send_msg"] == [dict(oid="oid1", content="夫君辛苦啦", msg_id="MID", msg_seq=1)]
    assert cap["send_voice"] == [dict(oid="oid1", fi="FI-xxx", msg_id="MID", msg_seq=2)]


async def test_emotion_disabled(monkeypatch):
    """emotion_enable=False:synth emotion 传空(不发 <|endofprompt|> 指令)"""
    cap = _mock_chain(monkeypatch)
    await _make_plugin({**DEFAULT_PARAMS, "emotion_enable": False}).on_message_out(_Ctx())
    assert cap["synth"]["emotion"] == ""


async def test_soft_fail_keeps_text(monkeypatch):
    """TTS 合成异常 → reply_sent 保持 False(webhook 发文本兜底),语音未发"""
    cap = _mock_chain(monkeypatch, synth_exc=RuntimeError("TTS 挂了"))
    ctx = _Ctx()
    await _make_plugin(DEFAULT_PARAMS).on_message_out(ctx)
    assert ctx.reply_sent is False
    assert cap["send_voice"] == []


async def test_stub_empty_mp3_skips(monkeypatch):
    """stub/空 mp3 → 跳过语音(reply_sent 不设,webhook 发文本)"""
    cap = _mock_chain(monkeypatch, mp3=b"")
    ctx = _Ctx()
    await _make_plugin(DEFAULT_PARAMS).on_message_out(ctx)
    assert ctx.reply_sent is False
    assert cap["upload"] == []


async def test_no_msg_id_skips(monkeypatch):
    """无 qq_msg_id(非被动回复)→ 不处理"""
    cap = _mock_chain(monkeypatch)
    ctx = _Ctx(qq_msg_id="")
    await _make_plugin(DEFAULT_PARAMS).on_message_out(ctx)
    assert ctx.reply_sent is False
    assert cap["send_voice"] == []


async def test_upload_base64_silk_and_voice_filetype(monkeypatch):
    """上传:file_type=3(VOICE),file_data = base64(silk bytes)"""
    silk = b"\x02SILKDATA"
    cap = _mock_chain(monkeypatch, silk=silk)
    await _make_plugin(DEFAULT_PARAMS).on_message_out(_Ctx())
    assert cap["upload"][0]["ft"] == api.FILE_TYPE_VOICE == 3
    assert cap["upload"][0]["data"] == base64.b64encode(silk).decode()


# —— REST params 端点(薄包装,get_plugin_manager mock)——
async def test_endpoint_get_set_params(monkeypatch):
    """GET 回显 params;PUT 调 set_object_config 存参数"""
    import api.rest_plugin as rp

    class FakeMgr:
        saved = None

        async def get_params(self, name, oid):
            return {"voice": "diana", "speed": 1.2}

        async def set_object_config(self, name, oid, enabled=None, params=None):
            FakeMgr.saved = (name, oid, enabled, params)

        def list_loaded(self):
            return ["tts_reply"]

    monkeypatch.setattr(rp, "get_plugin_manager", lambda: FakeMgr())
    got = await rp.get_plugin_params("tts_reply", "oid1")
    assert got == {"voice": "diana", "speed": 1.2}
    await rp.set_plugin_params("tts_reply", "oid1", params={"voice": "anna"})
    assert FakeMgr.saved == ("tts_reply", "oid1", None, {"voice": "anna"})


async def test_endpoint_params_not_found(monkeypatch):
    """插件未加载 → 404"""
    import api.rest_plugin as rp

    class EmptyMgr:
        def list_loaded(self):
            return []
    monkeypatch.setattr(rp, "get_plugin_manager", lambda: EmptyMgr())
    import pytest
    with pytest.raises(Exception):
        await rp.get_plugin_params("nope", "oid1")
