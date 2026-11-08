"""
表达类工具单测(2026-11-08 能力工具化批次)。
覆盖:SendVoice(合成+发送成功路径/合成失败返回原因不抛/空 text 短路)、
SendSticker(精确命中发图/未命中模糊匹配/低分拒绝)、_bigram_overlap 纯函数。
adapter/tts 全 mock,不发真 QQ 不真合成。

日期: 2026-11-08
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

from tools.base import ToolContext
from tools.expressive import SendStickerTool, SendVoiceTool, _bigram_overlap


class _FakeAdapter:
    """记录 send_voice/send_text 调用的假 adapter"""

    def __init__(self, voice_fail=False):
        self.voice_calls = []
        self.text_calls = []
        self.voice_fail = voice_fail

    async def send_voice(self, oid, audio, **kw):
        if self.voice_fail:
            raise RuntimeError("NapCat 未连接")
        self.voice_calls.append((oid, audio))

    async def send_text(self, oid, content, **kw):
        self.text_calls.append((oid, content))
        return {"delivered": True}


class _FakeTTS:
    def __init__(self, audio=b"ID3mp3"):
        self.audio = audio

    async def synthesize(self, text, voice, *a, **k):
        return self.audio


@pytest.fixture
def _wire(monkeypatch, tmp_path):
    """注入假 adapter/tts/redis(含 2 条假注册),返回各组件"""
    adapter_instance = _FakeAdapter()

    import adapter as adapter_module
    async def fake_adapter():
        return adapter_instance
    monkeypatch.setattr(adapter_module, "get_current_adapter", fake_adapter)

    import modality.tts as tts_mod
    monkeypatch.setattr(tts_mod, "get_tts", lambda: _FakeTTS())

    async def fake_resolve(redis, oid, fallback):
        return ""
    monkeypatch.setattr(tts_mod, "resolve_voice", fake_resolve)

    # 假 redis:lib 两条注册
    class _FR:
        def __init__(self):
            self.lib = {"a1.gif": "两个小人拥抱", "b2.png": "猫猫开心点头"}

        async def hgetall(self, key):
            return dict(self.lib) if key.endswith("lib") else {}

    import storage.redis_client as rc

    async def fake_gr():
        return _FR()

    monkeypatch.setattr(rc, "get_redis", fake_gr)
    # STICKER_DIR 指 tmp_path 并落两个假文件
    from storage import sticker_store
    monkeypatch.setattr(sticker_store, "STICKER_DIR", tmp_path)
    for name in ("a1.gif", "b2.png"):
        (tmp_path / name).write_bytes(b"x")
    return {"adapter": adapter_instance, "tmp": tmp_path}


def test_bigram_overlap():
    """bigram 交并比:相同=1/无关=0/部分重叠中间值"""
    assert _bigram_overlap("两个小人拥抱", "两个小人拥抱") == 1.0
    assert _bigram_overlap("猫猫点头", "完全不同的内容啊") == 0.0
    s = _bigram_overlap("小人在拥抱", "两个小人在拥抱")
    assert 0.0 < s < 1.0


async def test_send_voice_success(_wire):
    """合成+发送成功:返回成功说明,adapter 收到音频"""
    tool = SendVoiceTool()
    out = await tool.execute({"text": "想你了~"}, ToolContext(redis=None, object_id="10001"))
    assert "已把这段话用语音发给对方" in out
    assert _wire["adapter"].voice_calls and _wire["adapter"].voice_calls[0][0] == "10001"


async def test_send_voice_synth_fail_returns_reason(_wire, monkeypatch):
    """合成失败(如每日上限)→返回原因文本给模型,不抛异常不阻塞"""
    import modality.tts as tts_mod

    class _FailTTS:
        async def synthesize(self, *a, **k):
            raise RuntimeError("BreezeBlue 每日用量上限(40)已满")

    monkeypatch.setattr(tts_mod, "get_tts", lambda: _FailTTS())
    tool = SendVoiceTool()
    out = await tool.execute({"text": "想你了"}, ToolContext(redis=None, object_id="10001"))
    assert "语音发送失败" in out and "每日用量上限" in out
    assert _wire["adapter"].voice_calls == []


async def test_send_voice_empty_text(_wire):
    """空 text → 短路"""
    tool = SendVoiceTool()
    out = await tool.execute({"text": "  "}, ToolContext(redis=None, object_id="10001"))
    assert "text 为空" in out


async def test_send_sticker_exact_hit(_wire):
    """描述精确命中库 → 发出 token 文本(出站翻译层负责转图)"""
    tool = SendStickerTool()
    out = await tool.execute({"description": "两个小人拥抱"}, ToolContext(redis=None, object_id="10001"))
    assert "已把表情包发给对方" in out
    oid, content = _wire["adapter"].text_calls[-1]
    assert "[表情包: 两个小人拥抱]" in content


async def test_send_sticker_fuzzy_and_reject(_wire):
    """未精确命中 → bigram 模糊(「猫猫开心」≈「猫猫开心点头」0.67 应中);完全无关 → 拒绝"""
    tool = SendStickerTool()
    out = await tool.execute({"description": "猫猫开心"}, ToolContext(redis=None, object_id="10001"))
    assert "已把表情包发给对方" in out           # 模糊命中(b2.png)
    out2 = await tool.execute({"description": "火箭发射升空"}, ToolContext(redis=None, object_id="10001"))
    assert "没有接近" in out2                     # 零重叠拒绝,不发送
