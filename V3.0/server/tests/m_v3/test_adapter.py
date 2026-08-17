"""
适配器层单测(V3.0,2026-08-17 精简为纯 onebot):
1. 工厂恒返 OnebotAdapter
2. OnebotAdapter:文本过/跳过出站守卫、CQ 注入防护(array 格式)、失败抛异常、语音 record 段构造

作者: 李文煜
日期: 2026-08-16

2026-08-17
变更说明：
  1. 精简:删 official 工厂/透传测试(官方栈已裁撤,V3.0 恒 onebot)
"""
import pytest

import adapter


@pytest.fixture(autouse=True)
def _reset():
    adapter.reset_adapter()
    yield
    adapter.reset_adapter()


async def test_factory_returns_onebot():
    """工厂:恒返 OnebotAdapter(V3.0 纯 onebot,无配置分支)"""
    a = await adapter.get_current_adapter()
    from adapter.onebot import OnebotAdapter
    assert isinstance(a, OnebotAdapter)


async def test_onebot_text_guard_and_failure(monkeypatch):
    """onebot 文本:非 human_authored 过 sanitize 守卫;CQ 注入防护(array 格式);失败抛 RuntimeError"""
    from adapter.onebot import OnebotAdapter
    from adapter import reply_guard

    sent = []

    async def fake_call(action, params, timeout=None):
        sent.append((action, params))
        return {"status": "ok", "retcode": 0}

    monkeypatch.setattr("onebot.ws_client.call_action", fake_call)
    a = OnebotAdapter()

    def _text_of(params):
        """提取 array message 的 text 段"""
        segs = params["message"]
        assert isinstance(segs, list)                       # 审查#2:array 格式(免 CQ 解析)
        return segs[0]["data"]["text"]

    # ① 机器产出:含错误签名文本被守卫降级(不原样出站)
    bad = "Traceback (most recent call last): Client error 429"
    await a.send_text("12345", bad)
    assert _text_of(sent[-1][1]) == reply_guard.sanitize_reply(bad)
    assert _text_of(sent[-1][1]) != bad   # 确实被改写(守卫生效)

    # ② human_authored=True:原文出站(admin 代答);含 [CQ:...] 字面量也不被解析(array 格式)
    cq = "看 [CQ:image,file=x.jpg] 这段"
    await a.send_text("12345", cq, human_authored=True)
    assert _text_of(sent[-1][1]) == cq
    assert sent[-1][1]["user_id"] == 12345   # oid 字符串转 int

    # ③ call_action 失败(retcode!=0)→ RuntimeError(调用方降级逻辑依赖异常)
    async def fail_call(action, params, timeout=None):
        return {"status": "failed", "retcode": 1200}
    monkeypatch.setattr("onebot.ws_client.call_action", fail_call)
    with pytest.raises(RuntimeError):
        await a.send_text("12345", "hi")


async def test_onebot_voice_segments(monkeypatch):
    """onebot 语音:array record 段 + base64;可选 text 附文段(免 CQ 解析)"""
    from adapter.onebot import OnebotAdapter
    sent = []

    async def fake_call(action, params, timeout=None):
        sent.append((action, params))
        return {"status": "ok", "retcode": 0}

    monkeypatch.setattr("onebot.ws_client.call_action", fake_call)
    a = OnebotAdapter()
    import base64
    silk = b"\x01\x02silk-bytes"
    await a.send_voice("12345", silk, content="看这个")
    segs = sent[-1][1]["message"]
    assert segs[0] == {"type": "text", "data": {"text": "看这个"}}
    assert segs[1]["type"] == "record"
    assert segs[1]["data"]["file"] == f"base64://{base64.b64encode(silk).decode()}"
    # 无附文:纯 record 段
    await a.send_voice("12345", silk)
    assert sent[-1][1]["message"][0]["type"] == "record"
