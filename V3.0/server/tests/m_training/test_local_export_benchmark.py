"""
训练前置工具单测(2026-09-12 前置工作 A1/A2/B1):
1. LocalLLMProvider:同步 httpx mock 调用 / <think> 剥除 / registry 注册
2. export:SFT(pos/manual/correction/roleplay)+ DPO(correction 对)构造与 JSONL 落盘
3. benchmark:A/B provider 同上下文对比 + 固定裁判打分聚合

作者: 李文煜
日期: 2026-09-12

2026-10-25
变更说明：
  1. 关思考改造测试:原生 /api/chat 分支(payload+响应归一化+tool_calls dict→str)、
     原生失败回退 OpenAI 兼容路径+/no_think 注入、开关关闭走原路径
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
    """local provider:关思考开关关(disable_think=False)走 OpenAI 兼容原路径,
    <think> 段剥除,payload 带 think=False(被 Ollama 忽略,故须开关配合)"""
    import httpx
    import llm.local as local_mod
    from llm.local import LocalLLMProvider, _strip_think
    monkeypatch.setattr(settings, "local_llm_api_base", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(settings, "local_llm_model", "qwen3:8b")
    monkeypatch.setattr(settings, "local_llm_disable_think", False)
    _FakeSyncClient.calls.clear()
    monkeypatch.setattr(local_mod.httpx, "Client", _FakeSyncClient)

    p = LocalLLMProvider(api_key="")
    assert p.base_url == "http://127.0.0.1:11434/v1"
    from llm.base import Message
    resp = await p.chat([Message(role="user", content="在吗")])
    assert resp.text == "嗯嗯在的~"                       # think 段已剥
    call = _FakeSyncClient.calls[0]
    assert call["url"].endswith("/chat/completions")      # 原路径(未走原生 /api/chat)
    assert call["json"]["model"] == "qwen3:8b"
    assert call["json"]["think"] is False                 # 关思考参数(兼容路径带,旧版忽略)
    assert call["json"]["messages"][0]["content"] == "在吗"  # 开关关:不注入 /no_think
    # 未闭合 think 容错
    assert "思考" not in _strip_think("<think>abc</think>正文")


# ================ A1-2026-10-25: 关思考改造(原生 /api/chat + 回退注入) ================

class _NativeClient:
    """mock httpx.Client:Ollama 原生 /api/chat 形状响应(顶层 message/done_reason)"""

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        _NativeClient.last_url = url
        _NativeClient.last_json = json
        return _FakeResp({"model": "qwen3:8b",
                          "message": {"role": "assistant",
                                     "content": "<think>想想</think>嗯嗯我在本机运行~"},
                          "done_reason": "stop", "eval_count": 20})


async def test_local_provider_native_chat(monkeypatch):
    """开关开(默认):走原生 /api/chat,payload think=False 生效,响应归一化+剥 think 段"""
    import llm.local as local_mod
    from llm.local import LocalLLMProvider
    monkeypatch.setattr(settings, "local_llm_api_base", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(settings, "local_llm_model", "qwen3:8b")
    monkeypatch.setattr(settings, "local_llm_disable_think", True)
    monkeypatch.setattr(local_mod.httpx, "Client", _NativeClient)

    p = LocalLLMProvider(api_key="")
    from llm.base import Message
    resp = await p.chat([Message(role="user", content="用一句中文说你在本机运行")])
    # base_url 去掉末尾 /v1 拼 <root>/api/chat
    assert _NativeClient.last_url == "http://127.0.0.1:11434/api/chat"
    assert _NativeClient.last_json["think"] is False       # 原生端点真正生效的关思考参数
    assert _NativeClient.last_json["stream"] is False
    assert _NativeClient.last_json["model"] == "qwen3:8b"
    # 原生路径不注入 /no_think
    assert _NativeClient.last_json["messages"][0]["content"] == "用一句中文说你在本机运行"
    # done_reason 归一化到 finish_reason;content 归一化并剥 think 段
    assert resp.text == "嗯嗯我在本机运行~"
    assert resp.finish_reason == "stop"


async def test_local_provider_native_tool_calls_dict_args(monkeypatch):
    """原生 tool_calls:arguments 为 dict 时 json.dumps 成 str(JSON),与 OpenAI 路径一致"""
    import json as json_mod    # 仅避免与 post(json=...) 参数名混淆的本地别名(顶部已有 import json)
    import llm.local as local_mod
    from llm.local import LocalLLMProvider

    class _ToolClient(_NativeClient):
        def post(self, url, headers=None, json=None):
            _ToolClient.last_url = url
            _ToolClient.last_json = json
            return _FakeResp({"message": {"role": "assistant", "content": "",
                                          "tool_calls": [
                                              {"function": {"name": "get_weather",
                                                            "arguments": {"city": "北京"}}}]},
                              "done_reason": "tool_calls", "eval_count": 15})

    monkeypatch.setattr(settings, "local_llm_api_base", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(settings, "local_llm_disable_think", True)
    monkeypatch.setattr(local_mod.httpx, "Client", _ToolClient)

    p = LocalLLMProvider(api_key="")
    resp = await p.chat_with_tools(
        [{"role": "user", "content": "北京天气"}], tools=[{"type": "function"}])
    # tools/tool_choice 透传给原生端点
    assert _ToolClient.last_json["tools"] == [{"type": "function"}]
    assert _ToolClient.last_json["tool_choice"] == "auto"
    assert len(resp.tool_calls) == 1
    tc = resp.tool_calls[0]
    assert tc["name"] == "get_weather"
    assert isinstance(tc["arguments"], str)                # dict 已转 str
    assert json_mod.loads(tc["arguments"]) == {"city": "北京"}
    assert resp.finish_reason == "tool_calls"


class _FallbackClient:
    """mock httpx.Client:/api/chat 抛 ConnectError → 回退 /chat/completions 成功"""
    calls: list[dict] = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None):
        import httpx
        _FallbackClient.calls.append({"url": url, "json": json})
        if url.endswith("/api/chat"):
            raise httpx.ConnectError("vLLM 无原生端点")    # 触发回退
        return _FakeResp({"choices": [{"message": {"content": "在的~"}, "finish_reason": "stop"}]})


async def test_local_provider_fallback_injects_no_think(monkeypatch):
    """回退:原生端点 ConnectError → OpenAI 兼容路径,末条 user 消息注入 " /no_think" """
    import llm.local as local_mod
    from llm.local import LocalLLMProvider
    monkeypatch.setattr(settings, "local_llm_api_base", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(settings, "local_llm_disable_think", True)
    _FallbackClient.calls.clear()
    monkeypatch.setattr(local_mod.httpx, "Client", _FallbackClient)

    p = LocalLLMProvider(api_key="")
    from llm.base import Message
    resp = await p.chat([Message(role="system", content="你是清浔"),
                         Message(role="user", content="在吗"),
                         Message(role="assistant", content="嗯"),
                         Message(role="user", content="在忙什么")])
    assert len(_FallbackClient.calls) == 2                 # 先原生失败,再回退
    assert _FallbackClient.calls[0]["url"].endswith("/api/chat")
    fb = _FallbackClient.calls[1]
    assert fb["url"].endswith("/chat/completions")
    msgs = fb["json"]["messages"]
    # 注入到"最后一条"user(在忙什么),不是第一条 user(在吗);system 不动
    assert msgs[1]["content"] == "在吗"
    assert msgs[3]["content"] == "在忙什么 /no_think"
    assert msgs[0]["content"] == "你是清浔"
    assert resp.text == "在的~"


async def test_local_provider_fallback_http_status_and_system_inject(monkeypatch):
    """回退二连:① /api/chat 404(HTTPStatusError)同样触发回退;
    ② 无 user 消息时 /no_think 注入到末条 system 末尾"""
    import httpx
    import llm.local as local_mod
    from llm.local import LocalLLMProvider

    class _NotFoundClient(_FallbackClient):
        calls: list[dict] = []   # 独立记录(不复用父类共享列表)

        def post(self, url, headers=None, json=None):
            _NotFoundClient.calls.append({"url": url, "json": json})
            if url.endswith("/api/chat"):
                req = httpx.Request("POST", url)           # raise_for_status 构造错误所需
                resp = httpx.Response(404, request=req)    # vLLM 对未知路径返 404
                resp.raise_for_status()
            return _FakeResp({"choices": [{"message": {"content": "好的"}, "finish_reason": "stop"}]})

    monkeypatch.setattr(settings, "local_llm_api_base", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(settings, "local_llm_disable_think", True)
    _NotFoundClient.calls.clear()
    monkeypatch.setattr(local_mod.httpx, "Client", _NotFoundClient)

    p = LocalLLMProvider(api_key="")
    from llm.base import Message
    resp = await p.chat([Message(role="system", content="你是清浔")])
    assert len(_NotFoundClient.calls) == 2                 # 404 也回退
    assert _NotFoundClient.calls[1]["url"].endswith("/chat/completions")
    # 无 user:注入 system 末尾
    assert _NotFoundClient.calls[1]["json"]["messages"][0]["content"] == "你是清浔 /no_think"
    assert resp.text == "好的"


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
    # 每条隔 30ms:防同毫秒 ts ZSet 平局(mid 字典序)排序抖动(老坑,Windows 时钟粒度 ~15ms)
    await cs.append_message(fake_redis, "10001", sender="user", content="早上好")
    await asyncio.sleep(0.03)
    mid_pos = await cs.append_message(fake_redis, "10001", sender="ai", content="早上好呀~今天也要元气满满")
    await cs.set_score(fake_redis, mid_pos, score_base=90, mood_value=0.5, mood_bias=0)
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="user", content="晚上吃什么")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="proxy", content="想吃火锅~",
                            source="manual")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="user", content="陪我聊会")
    await asyncio.sleep(0.03)
    mid_bad = await cs.append_message(fake_redis, "10001", sender="ai", content="好的。请问有什么可以帮您?")
    await cs.set_score(fake_redis, mid_bad, score_base=40, mood_value=0.5, mood_bias=0)
    await fake_redis.hset(f"mychat:msg:{mid_bad}", "corrected", "嗯嗯~夫君想聊什么呀")
    # roleplay 高分剧本(两条间隔 30ms:同毫秒 ts 时 ZSet 按 mid 字典序排,顺序随机翻转)
    await cs.append_roleplay_message(fake_redis, "10001", role="user", content="剧本问句")
    await asyncio.sleep(0.03)
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


# ================ B1-export 2026-09-15:连发合并(burst merge) ================

async def _seed_burst_chat(fake_redis):
    """连发场景:user + manual 三连发 + user + manual 单条 + user + 占位-only manual"""
    import asyncio
    from storage import chat_store as cs
    await cs.append_message(fake_redis, "10001", sender="user", content="在忙吗")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="proxy", content="在呀", source="manual")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="proxy", content="刚下课", source="manual")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="proxy", content="夫君吃饭了没", source="manual")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="user", content="那我先写作业啦")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="proxy", content="好呀~", source="manual")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="user", content="看看这个")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="proxy", content="[图片]", source="manual")


async def test_export_burst_merge(tmp_path, fake_redis, monkeypatch):
    """连发合并:三连发 manual 合并成 1 条 '\n' 样本;后续样本 history 携带合并版回合"""
    from training import export as export_mod
    monkeypatch.setattr(export_mod, "_training_dir", lambda: tmp_path)
    await _seed_burst_chat(fake_redis)

    r = await export_mod.export_training_data(fake_redis, "10001", min_score=85)
    # 三连发=1 条 + 单条=1 条;占位-only 的回复单元不成样本
    assert r["by_source"]["manual"] == 2

    sft_file = [p for p in tmp_path.iterdir() if "sft" in p.name][0]
    sft = [json.loads(x) for x in sft_file.read_text(encoding="utf-8").splitlines()]
    by_inst = {it["instruction"]: it for it in sft}
    # 三连发合并成一条,保持顺序
    assert by_inst["在忙吗"]["output"] == "在呀\n刚下课\n夫君吃饭了没"
    # 后续样本的前文携带合并版回合(多气泡=一条多行 assistant 回合)
    assert by_inst["那我先写作业啦"]["history"] == [["在忙吗", "在呀\n刚下课\n夫君吃饭了没"]]
    # 占位-only 手动回复不入集([图片] 对风格学习无价值)
    assert "看看这个" not in by_inst


async def test_export_burst_correction(tmp_path, fake_redis, monkeypatch):
    """correction 混入连发:merged 用纠正文本;DPO chosen/rejected 均为合并版(同上下文整回复对比)"""
    import asyncio
    from storage import chat_store as cs
    from training import export as export_mod
    monkeypatch.setattr(export_mod, "_training_dir", lambda: tmp_path)
    await cs.append_message(fake_redis, "10001", sender="user", content="说点什么")
    await asyncio.sleep(0.03)
    await cs.append_message(fake_redis, "10001", sender="proxy", content="嗯?", source="manual")
    await asyncio.sleep(0.03)
    mid_bad = await cs.append_message(fake_redis, "10001", sender="ai", content="请问有什么可以帮您?")
    await cs.set_score(fake_redis, mid_bad, score_base=40, mood_value=0.5, mood_bias=0)
    await fake_redis.hset(f"mychat:msg:{mid_bad}", "corrected", "夫君想我了吗~")

    r = await export_mod.export_training_data(fake_redis, "10001", min_score=85)
    assert r["by_source"]["correction"] == 1
    assert r["by_source"]["manual"] == 0            # burst 整单元归 correction(manual 部分并入)
    assert r["dpo"] == 1
    dpo_file = [p for p in tmp_path.iterdir() if "dpo" in p.name][0]
    dpo = [json.loads(x) for x in dpo_file.read_text(encoding="utf-8").splitlines()]
    # chosen=合并纠正版 / rejected=合并原版
    assert dpo[0]["chosen"]["value"] == "嗯?\n夫君想我了吗~"
    assert dpo[0]["rejected"]["value"] == "嗯?\n请问有什么可以帮您?"
    sft_file = [p for p in tmp_path.iterdir() if "sft" in p.name][0]
    sft = [json.loads(x) for x in sft_file.read_text(encoding="utf-8").splitlines()]
    assert sft[0]["output"] == "嗯?\n夫君想我了吗~"


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

    import asyncio as _aio
    await chat_store.append_message(fake_redis, "10001", sender="user", content="第一条")
    await _aio.sleep(0.03)
    await chat_store.append_message(fake_redis, "10001", sender="ai", content="回一")
    await _aio.sleep(0.03)
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
