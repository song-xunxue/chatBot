"""
score.service 单测:classify 阈值 / _parse_score 解析容错 / score_reply 全链路
(LLM 打分→mood 补偿→四元组写入→正负样本归类)/ 手动改分 / 取分 / 人设健康度。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 创建 score.service 单测(阈值/解析/score_reply 三档 mood/手动改分/健康度/样本收集)
"""
from core.config import settings
from storage import chat_store
from mood import service as mood_service
from persona.default import default_persona
from score import service as score_service


async def test_classify_thresholds():
    """阈值边界:>=85 positive / [60,85) neutral / <60 negative"""
    assert score_service.classify(85) == "positive"
    assert score_service.classify(100) == "positive"
    assert score_service.classify(84) == "neutral"
    assert score_service.classify(60) == "neutral"
    assert score_service.classify(59) == "negative"
    assert score_service.classify(0) == "negative"


def test_parse_score_pure_json():
    assert score_service._parse_score('{"score": 88, "reason": "好"}') == (88, "好")


def test_parse_score_with_surrounding_text():
    """LLM 输出带前后文本,仍能解析首个含 score 的 JSON"""
    assert score_service._parse_score('评分如下:\n{"score": 72, "reason": "一般"}\n完成') == (72, "一般")


def test_parse_score_clamps():
    """超出 [0,100] 截断"""
    assert score_service._parse_score('{"score": 150, "reason": "x"}')[0] == 100
    assert score_service._parse_score('{"score": -5, "reason": "x"}')[0] == 0


def test_parse_score_invalid_returns_none():
    assert score_service._parse_score("no json here") is None
    assert score_service._parse_score('{"reason": "无分"}') is None   # 缺 score 键


def _wire_provider(monkeypatch, make_provider, json_text):
    """公用:装 key + 注入返回 json_text 的 mock provider 到 score.service.get_provider"""
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    provider = make_provider(json_text)
    monkeypatch.setattr("score.service.get_provider", lambda name: provider)
    return provider


async def test_score_reply_calm_positive(fake_redis, make_provider, monkeypatch):
    """score_reply:base=90 + mood calm(0.5,bias 0±3)→ score∈[87,93] → positive 样本"""
    await mood_service.seed_default_kinds(fake_redis)
    await mood_service.set_mood(fake_redis, "u1", 0.5)
    _wire_provider(monkeypatch, make_provider, '{"score": 90, "reason": "契合人设"}')

    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="温柔回复")
    quad = await score_service.score_reply(fake_redis, "u1", "温柔回复",
                                           default_persona(), mid, mood_value=0.5)
    assert quad["score_base"] == 90
    assert quad["mood_at_score"] == 0.5
    assert 87 <= quad["score"] <= 93
    assert quad["score_reason"] == "契合人设"

    got = await score_service.get_score(fake_redis, mid)
    assert got["score_base"] == 90
    pos = await score_service.list_samples(fake_redis, "u1", "positive")
    assert len(pos) == 1 and pos[0]["text"] == "温柔回复"


async def test_score_reply_negative(fake_redis, make_provider, monkeypatch):
    """低分(base=40)归类 negative 并收集到 neg 样本,pos 样本空"""
    await mood_service.seed_default_kinds(fake_redis)
    _wire_provider(monkeypatch, make_provider, '{"score": 40, "reason": "偏离"}')

    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="冷漠回复")
    quad = await score_service.score_reply(fake_redis, "u1", "冷漠回复",
                                           default_persona(), mid, mood_value=0.5)
    assert 37 <= quad["score"] <= 43
    assert await score_service.list_samples(fake_redis, "u1", "negative") != []
    assert await score_service.list_samples(fake_redis, "u1", "positive") == []


async def test_score_reply_happy_bias(fake_redis, make_provider, monkeypatch):
    """mood=happy(0.9,bias +6±3):base=80 → score∈[83,89],mood_bias∈[3,9]"""
    await mood_service.seed_default_kinds(fake_redis)
    await mood_service.set_mood(fake_redis, "u1", 0.9)
    _wire_provider(monkeypatch, make_provider, '{"score": 80, "reason": "ok"}')

    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
    quad = await score_service.score_reply(fake_redis, "u1", "x", default_persona(), mid, mood_value=0.9)
    assert 83 <= quad["score"] <= 89
    assert 3 <= quad["mood_bias"] <= 9


async def test_score_reply_no_provider_degrades(fake_redis, monkeypatch):
    """无可用 provider(key 空)→ 返回 None,不写分(降级)"""
    await mood_service.seed_default_kinds(fake_redis)
    # _no_real_llm 已清空 key → available_providers()=[]
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
    assert await score_service.score_reply(fake_redis, "u1", "x", default_persona(), mid) is None
    assert (await score_service.get_score(fake_redis, mid))["score"] is None


async def test_score_reply_llm_garbage_degrades(fake_redis, make_provider, monkeypatch):
    """LLM 返回非 JSON → _parse_score 返回 None → score_reply 返回 None(降级,不抛)"""
    await mood_service.seed_default_kinds(fake_redis)
    _wire_provider(monkeypatch, make_provider, "我无法评分")
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
    assert await score_service.score_reply(fake_redis, "u1", "x", default_persona(), mid) is None


async def test_manual_set_score_keeps_mood_bias(fake_redis, make_provider, monkeypatch):
    """手动改 base,保留原 mood_bias,重算 score,标记 score_manual"""
    await mood_service.seed_default_kinds(fake_redis)
    _wire_provider(monkeypatch, make_provider, '{"score": 90, "reason": "好"}')
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
    orig = await score_service.score_reply(fake_redis, "u1", "x", default_persona(), mid, mood_value=0.5)
    bias_before = orig["mood_bias"]

    new = await score_service.manual_set_score(fake_redis, mid, 50)
    assert new["score_base"] == 50
    assert new["mood_bias"] == bias_before                       # 保留历史 mood_bias
    assert new["score"] == max(0, min(100, round(50 + bias_before)))
    got = await score_service.get_score(fake_redis, mid)
    assert got["score_manual"] == "1"


async def test_manual_set_score_clamps_base(fake_redis):
    """手动 base 超 [0,100] 截断"""
    await mood_service.seed_default_kinds(fake_redis)
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
    new = await score_service.manual_set_score(fake_redis, mid, 200)
    assert new["score_base"] == 100


async def test_manual_set_score_not_found(fake_redis):
    assert await score_service.manual_set_score(fake_redis, "nope", 80) is None


async def test_get_score_not_found(fake_redis):
    assert await score_service.get_score(fake_redis, "nope") is None


async def test_persona_health_stats(fake_redis):
    """近 N 条 ai 消息均分 + 正/负/中计数(user 消息不计)"""
    await mood_service.seed_default_kinds(fake_redis)
    for sc in (90, 70, 40):
        mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
        await chat_store.set_score(fake_redis, mid, score_base=sc, mood_value=0.5, mood_bias=0)
    # 混入一条 user 消息(不应计入健康度)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="问")

    health = await score_service.persona_health(fake_redis, "u1", window=10)
    assert health["count"] == 3
    assert health["avg_score"] == round((90 + 70 + 40) / 3, 1)   # 66.7
    assert health["positive"] == 1
    assert health["negative"] == 1
    assert health["neutral"] == 1


async def test_persona_health_window(fake_redis):
    """window 截断:只取最近 N 条有分的"""
    await mood_service.seed_default_kinds(fake_redis)
    for sc in (90, 80, 70, 60):
        mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x")
        await chat_store.set_score(fake_redis, mid, score_base=sc, mood_value=0.5, mood_bias=0)
    health = await score_service.persona_health(fake_redis, "u1", window=2)   # 最近 2 条:70,60
    assert health["count"] == 2
    assert health["avg_score"] == 65.0


async def test_persona_health_empty(fake_redis):
    health = await score_service.persona_health(fake_redis, "u1")
    assert health["count"] == 0 and health["avg_score"] is None
