"""
训练前置工具单测(2026-09-12 前置工作 A1/A2/B1):
1. LocalLLMProvider:同步 httpx mock 调用 / <think> 剥除 / registry 注册
2. export:SFT(pos/manual/correction/roleplay)+ DPO(correction 对)构造与 JSONL 落盘
3. benchmark:A/B provider 同上下文对比 + 固定裁判打分聚合

作者: 李文煜
日期: 2026-09-12
"""
import json

import pytest

from core.config import settings
from storage import chat_store


# ================ A1: LocalLLMProvider ================

class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeSyncClient:
    """mock httpx.Client(同步,LocalLLMProvider 在 to_thread 里用)"""
    calls: list[dict] = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        _FakeSyncClient.calls.append({"url": url, "json": json})
        content = "<think>先想一想</think>嗯嗯在的~"
        return _FakeResp({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})


async def test_local_provider_chat_strips_think(monkeypatch):
    """local provider:chat 走同步 client(mock),<think> 段剥除,payload 带 think=False"""
    import httpx
    import llm.local as local_mod
    from llm.local import LocalLLMProvider, _strip_think
    monkeypatch.setattr(settings, "local_llm_api_base", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(settings, "local_llm_model", "qwen3:8b")
    _FakeSyncClient.calls.clear()
    monkeypatch.setattr(local_mod.httpx, "Client", _FakeSyncClient)

    p = LocalLLMProvider(api_key="")
    assert p.base_url == "http://127.0.0.1:11434/v1"
    from llm.base import Message
    resp = await p.chat([Message(role="user", content="在吗")])
    assert resp.text == "嗯嗯在的~"                       # think 段已剥
    call = _FakeSyncClient.calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["json"]["model"] == "qwen3:8b"
    assert call["json"]["think"] is False                 # 关思考参数
    # 未闭合 think 容错
    assert "思考" not in _strip_think("<think>abc</think>正文")


async def test_local_provider_in_registry():
    """registry:local 已注册,get_provider 可实例化"""
    from llm.registry import get_provider, provider_specs
    names = [s.name for s in provider_specs()]
    assert "local" in names
    p = get_provider("local")
    assert p is not None


# ================ B1: export ================

async def _seed_chat(fake_redis):
    """造对话:user+ai(90=pos) / user+proxy(manual) / user+ai(低分+corrected=correction+DPO)"""
    import asyncio
    from storage import chat_store as cs
    # 每条隔 2ms:防同毫秒 ts ZSet 平局排序抖动(老坑)
    await cs.append_message(fake_redis, "10001", sender="user", content="早上好")
    await asyncio.sleep(0.002)
    mid_pos = await cs.append_message(fake_redis, "10001", sender="ai", content="早上好呀~今天也要元气满满")
    await cs.set_score(fake_redis, mid_pos, score_base=90, mood_value=0.5, mood_bias=0)
    await asyncio.sleep(0.002)
    await cs.append_message(fake_redis, "10001", sender="user", content="晚上吃什么")
    await asyncio.sleep(0.002)
    await cs.append_message(fake_redis, "10001", sender="proxy", content="想吃火锅~",
                            source="manual")
    await asyncio.sleep(0.002)
    await cs.append_message(fake_redis, "10001", sender="user", content="陪我聊会")
    await asyncio.sleep(0.002)
    mid_bad = await cs.append_message(fake_redis, "10001", sender="ai", content="好的。请问有什么可以帮您?")
    await cs.set_score(fake_redis, mid_bad, score_base=40, mood_value=0.5, mood_bias=0)
    await fake_redis.hset(f"mychat:msg:{mid_bad}", "corrected", "嗯嗯~夫君想聊什么呀")
    # roleplay 高分剧本
    await cs.append_roleplay_message(fake_redis, "10001", role="user", content="剧本问句")
    await cs.append_roleplay_message(fake_redis, "10001", role="assistant",
                                     content="剧本高分回复~", score_base=90)


async def test_export_training_data(tmp_path, fake_redis, monkeypatch):
    """导出:SFT 含 pos/manual/correction/roleplay 四类;DPO 仅 correction 对;JSONL 结构正确"""
    from training import export as export_mod
    monkeypatch.setattr(export_mod, "_training_dir", lambda: tmp_path)
    await _seed_chat(fake_redis)

    r = await export_mod.export_training_data(fake_redis, "10001", min_score=85)
    # 统计:pos=1 manual=1 correction=1 roleplay=1 dpo_pairs=1
    assert r["by_source"]["pos"] == 1
    assert r["by_source"]["manual"] == 1
    assert r["by_source"]["correction"] == 1
    assert r["by_source"]["roleplay"] == 1
    assert r["by_source"]["dpo_pairs"] == 1
    assert r["sft"] == 4 and r["dpo"] == 1

    sft_file = [p for p in tmp_path.iterdir() if "sft" in p.name][0]
    dpo_file = [p for p in tmp_path.iterdir() if "dpo" in p.name][0]
    sft = [json.loads(x) for x in sft_file.read_text(encoding="utf-8").splitlines()]
    dpo = [json.loads(x) for x in dpo_file.read_text(encoding="utf-8").splitlines()]

    # alpaca 结构 + system 含人设
    outputs = {it["output"] for it in sft}
    assert outputs == {"早上好呀~今天也要元气满满", "想吃火锅~", "嗯嗯~夫君想聊什么呀", "剧本高分回复~"}
    assert all(it["system"] and "输出契约" in it["system"] for it in sft)
    assert all(set(it.keys()) >= {"instruction", "output", "system", "history"} for it in sft)
    # 低分未纠正的 ai 回复不入集
    assert "好的。请问有什么可以帮您?" not in outputs
    # DPO 偏好对:chosen=纠正文本 / rejected=原低分回复,sharegpt 结构
    assert len(dpo) == 1
    assert dpo[0]["chosen"]["value"] == "嗯嗯~夫君想聊什么呀"
    assert dpo[0]["rejected"]["value"] == "好的。请问有什么可以帮您?"
    assert dpo[0]["conversations"][0]["from"] == "system"
    assert dpo[0]["conversations"][-1]["value"] == "陪我聊会"


# ================ A2: benchmark ================

async def test_benchmark_persona(fake_redis, monkeypatch):
    """盲测:两 fake provider 各产回复,固定裁判(mock _llm_score)打分,聚合均分"""
    from llm.base import LLMResponse, Message
    from training import benchmark as bm

    class _FakeProvider:
        def __init__(self, text):
            self.text = text

        async def chat(self, messages, model="", **opts):
            return LLMResponse(text=self.text)

    async def _fake_score(reply_text, persona_card, provider_name, model):
        return (95 if "好" in reply_text else 55, "理由")

    monkeypatch.setattr(bm, "get_provider", lambda name: _FakeProvider(f"{name} 的好回复"))
    import score.service as score_service
    monkeypatch.setattr(score_service, "_llm_score", _fake_score)

    await chat_store.append_message(fake_redis, "10001", sender="user", content="第一条")
    await chat_store.append_message(fake_redis, "10001", sender="ai", content="回一")
    await chat_store.append_message(fake_redis, "10001", sender="user", content="第二条")

    r = await bm.benchmark_persona(fake_redis, "10001",
                                   provider_a="glm", provider_b="local", n=10)
    assert r["n"] == 2                                     # 两条 user 消息
    assert r["a"]["provider"] == "glm" and r["b"]["provider"] == "local"
    assert r["a"]["avg"] == 95.0 and r["b"]["avg"] == 95.0  # fake 回复都含"好"
    assert r["a"]["count"] == 2 and r["a"]["errors"] == 0
    assert len(r["samples"]) == 2
    assert r["samples"][0]["user"] == "第一条"


async def test_benchmark_generation_error_counted(fake_redis, monkeypatch):
    """盲测:A provider 持续抛错 → 计入 errors,均分为 None,不中断"""
    from llm.base import LLMResponse
    from training import benchmark as bm

    class _BoomProvider:
        async def chat(self, messages, model="", **opts):
            raise RuntimeError("frp 断了")

    class _OkProvider:
        async def chat(self, messages, model="", **opts):
            return LLMResponse(text="正常回复")

    providers = {"glm": _BoomProvider(), "local": _OkProvider()}
    monkeypatch.setattr(bm, "get_provider", lambda name: providers[name])

    async def _fake_score(reply_text, persona_card, provider_name, model):
        return (80, "")

    import score.service as score_service
    monkeypatch.setattr(score_service, "_llm_score", _fake_score)
    await chat_store.append_message(fake_redis, "10001", sender="user", content="问")
    r = await bm.benchmark_persona(fake_redis, "10001",
                                   provider_a="glm", provider_b="local", n=5)
    assert r["a"]["errors"] == 1 and r["a"]["avg"] is None
    assert r["b"]["avg"] == 80.0 and r["b"]["errors"] == 0
