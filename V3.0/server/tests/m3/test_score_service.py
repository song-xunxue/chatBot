"""
score.service 单测:classify 阈值 / _parse_score 解析容错 / score_reply 全链路
(LLM 打分→mood 补偿→四元组写入→正负样本归类)/ 手动改分 / 取分 / 人设健康度。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M3 创建 score.service 单测(阈值/解析/score_reply 三档 mood/手动改分/健康度/样本收集)

2026-09-07
变更说明:
  1. 新增 force_positive 用例(手动回复恒正样本:LLM 中性分仍正样本 100/无 LLM 仍收样本)
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
    """公用:装 key + 注入返回 json_text 的 mock provider 到 score.service.resolve_provider"""
    monkeypatch.setattr(settings, "glm_api_key", "fake-key")
    provider = make_provider(json_text)
    monkeypatch.setattr("score.service.resolve_provider", lambda *a, **k: provider)
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


async def test_score_reply_force_positive(fake_redis, make_provider, monkeypatch):
    """force_positive(2026-09-07 手动回复):LLM 打 62(中性区间)四元组照算,
    但样本恒正 source='manual' score=100(不参与 classify),neg 空"""
    await mood_service.seed_default_kinds(fake_redis)
    await mood_service.set_mood(fake_redis, "u1", 0.5)
    _wire_provider(monkeypatch, make_provider, '{"score": 62, "reason": "偏短"}')

    mid = await chat_store.append_message(fake_redis, "u1", sender="proxy", content="嗯嗯")
    quad = await score_service.score_reply(fake_redis, "u1", "嗯嗯", default_persona(), mid,
                                           mood_value=0.5, force_positive=True)
    assert quad["score_base"] == 62                     # 四元组照算(展示/健康度)
    pos = await score_service.list_samples(fake_redis, "u1", "positive")
    assert len(pos) == 1 and pos[0]["source"] == "manual" and pos[0]["score"] == 100
    assert await score_service.list_samples(fake_redis, "u1", "negative") == []


async def test_score_reply_force_positive_no_llm(fake_redis, monkeypatch):
    """force_positive + LLM 不可用(无 provider,根 conftest 已清 key):四元组 None 但正样本仍收
    (黄金标准不依赖 LLM 可用性)"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="proxy", content="嗯")
    quad = await score_service.score_reply(fake_redis, "u1", "嗯", default_persona(), mid,
                                           mood_value=0.5, force_positive=True)
    assert quad is None
    pos = await score_service.list_samples(fake_redis, "u1", "positive")
    assert len(pos) == 1 and pos[0]["source"] == "manual" and pos[0]["score"] == 100


async def test_score_reply_force_positive_placeholder_not_sampled(fake_redis, monkeypatch):
    """审查修复(2026-09-07):占位文本([语音]/[图片]等)不作黄金正样本(对反推无价值,
    反而污染权威样本池);无 LLM 路径同样不收"""
    mid = await chat_store.append_message(fake_redis, "u1", sender="proxy", content="[语音]")
    quad = await score_service.score_reply(fake_redis, "u1", "[语音]", default_persona(), mid,
                                           mood_value=0.5, force_positive=True)
    assert quad is None
    assert await score_service.list_samples(fake_redis, "u1", "positive") == []


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


async def test_manual_set_score_corrected(fake_redis):
    """2026-08-18:纠正回复——原 content 保留不动;corrected 写消息字段 + 正样本
    (source=correction)进 pos 队列;低分原文进 neg 队列(双样本驱动反推)。
    2026-08-18 #2:corrected_score 自定义纠正分数(默认 100,恒正样本)"""
    await mood_service.seed_default_kinds(fake_redis)
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="原回复(不够拟人)")
    new = await score_service.manual_set_score(fake_redis, mid, 40, corrected="换成角色口吻的理想回复",
                                               corrected_score=95)
    assert new["score_base"] == 40                       # score=base+bias 不精确断言
    assert new.get("corrected") == "换成角色口吻的理想回复"
    assert new.get("corrected_score") == 95
    msg = await chat_store.get_message(fake_redis, mid)
    assert msg["content"] == "原回复(不够拟人)"                     # 原内容保留
    assert msg["corrected"] == "换成角色口吻的理想回复"
    assert msg["corrected_score"] == "95"
    got = await score_service.get_score(fake_redis, mid)
    assert got["corrected"] == "换成角色口吻的理想回复"
    assert got["corrected_score"] == 95
    pos = await score_service.list_samples(fake_redis, "u1", "positive")
    neg = await score_service.list_samples(fake_redis, "u1", "negative")
    assert any(s["source"] == "correction" and s["text"] == "换成角色口吻的理想回复"
               and s["score"] == 95 for s in pos)
    assert any(s["source"] == "dialog" and s["text"] == "原回复(不够拟人)" for s in neg)
    # 未传 corrected_score → 默认 100
    mid2 = await chat_store.append_message(fake_redis, "u1", sender="ai", content="第二条")
    r2 = await score_service.manual_set_score(fake_redis, mid2, 30, corrected="默认百分")
    assert r2["corrected_score"] == 100
    pos2 = await score_service.list_samples(fake_redis, "u1", "positive")
    assert any(s["mid"] == mid2 and s["source"] == "correction" and s["score"] == 100 for s in pos2)


async def test_manual_set_score_resync_samples(fake_redis):
    """2026-08-18:手动改分按新 score 重收样本(修"手动打负分不进 neg 队列"缺口);
    重复改分清旧不残留;neutral 不收"""
    await mood_service.seed_default_kinds(fake_redis)
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="回复文本")
    await score_service.manual_set_score(fake_redis, mid, 40)       # 打负分 → neg
    neg = await score_service.list_samples(fake_redis, "u1", "negative")
    assert len(neg) == 1 and neg[0]["mid"] == mid and neg[0]["source"] == "dialog"
    await score_service.manual_set_score(fake_redis, mid, 95)       # 改高分 → neg 清,pos 进
    assert await score_service.list_samples(fake_redis, "u1", "negative") == []
    pos = await score_service.list_samples(fake_redis, "u1", "positive")
    assert len(pos) == 1 and pos[0]["mid"] == mid
    await score_service.manual_set_score(fake_redis, mid, 70)       # neutral → 两队列皆空
    assert await score_service.list_samples(fake_redis, "u1", "positive") == []
    assert await score_service.list_samples(fake_redis, "u1", "negative") == []


async def test_manual_set_score_corrected_clear_and_keep(fake_redis):
    """2026-08-18:corrected 缺省(None)=不动纠正字段(样本以已存纠正+分数重建);
    传空串=清除纠正与对应样本;只调 corrected_score(不重填文本)也落库"""
    await mood_service.seed_default_kinds(fake_redis)
    mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="原")
    await score_service.manual_set_score(fake_redis, mid, 40, corrected="纠正版")
    # 缺省 corrected:只改分,纠正保留(样本按已存纠正重建)
    await score_service.manual_set_score(fake_redis, mid, 50)
    msg = await chat_store.get_message(fake_redis, mid)
    assert msg["corrected"] == "纠正版"
    assert any(s["source"] == "correction" for s in
               await score_service.list_samples(fake_redis, "u1", "positive"))
    # 只调纠正分数:文本不动,分数更新,样本分数跟着变
    await score_service.manual_set_score(fake_redis, mid, 50, corrected_score=88)
    msg = await chat_store.get_message(fake_redis, mid)
    assert msg["corrected"] == "纠正版"
    assert msg["corrected_score"] == "88"
    pos = await score_service.list_samples(fake_redis, "u1", "positive")
    assert any(s["source"] == "correction" and s["score"] == 88 for s in pos)
    # 空串:清除纠正字段与 correction 样本(重收的 dialog 样本不受影响)
    await score_service.manual_set_score(fake_redis, mid, 50, corrected="")
    msg = await chat_store.get_message(fake_redis, mid)
    assert msg.get("corrected", "") == ""
    pos = await score_service.list_samples(fake_redis, "u1", "positive")
    assert not any(s["source"] == "correction" for s in pos)


async def test_get_score_not_found(fake_redis):
    assert await score_service.get_score(fake_redis, "nope") is None


async def test_persona_health_stats(fake_redis):
    """近 N 条 ai 消息均分 + 正/负/中计数(user 消息不计)"""
    await mood_service.seed_default_kinds(fake_redis)
    base = 1700000000000
    for i, sc in enumerate((90, 70, 40)):
        mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x", ts=base + i)
        await chat_store.set_score(fake_redis, mid, score_base=sc, mood_value=0.5, mood_bias=0)
    # 混入一条 user 消息(不应计入健康度)
    await chat_store.append_message(fake_redis, "u1", sender="user", content="问", ts=base + 99)

    health = await score_service.persona_health(fake_redis, "u1", window=10)
    assert health["count"] == 3
    assert health["avg_score"] == round((90 + 70 + 40) / 3, 1)   # 66.7
    assert health["positive"] == 1
    assert health["negative"] == 1
    assert health["neutral"] == 1


async def test_persona_health_window(fake_redis):
    """window 截断:只取最近 N 条有分的"""
    await mood_service.seed_default_kinds(fake_redis)
    base = 1700000000000
    for i, sc in enumerate((90, 80, 70, 60)):
        mid = await chat_store.append_message(fake_redis, "u1", sender="ai", content="x", ts=base + i)
        await chat_store.set_score(fake_redis, mid, score_base=sc, mood_value=0.5, mood_bias=0)
    health = await score_service.persona_health(fake_redis, "u1", window=2)   # 最近 2 条:70,60
    assert health["count"] == 2
    assert health["avg_score"] == 65.0


async def test_persona_health_empty(fake_redis):
    health = await score_service.persona_health(fake_redis, "u1")
    assert health["count"] == 0 and health["avg_score"] is None
