"""
mood service 单测:mood 读写/clamp/情感更新/档位查询/评分补偿/种表 CRUD 校验/衰减。
对应 docs/03 §3/§4/§5。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 创建 mood service 单测
"""
import pytest

from mood import service, decay


async def test_get_mood_default_neutral(fake_redis):
    """未设置 mood 返回中性 0.5"""
    assert await service.get_mood(fake_redis, "u1") == 0.5


async def test_set_get_mound(fake_redis):
    await service.set_mood(fake_redis, "u1", 0.8)
    assert await service.get_mood(fake_redis, "u1") == 0.8


async def test_set_mood_clamp(fake_redis):
    """mood 超 [0,1] 被 clamp"""
    await service.set_mood(fake_redis, "u1", 1.5)
    assert await service.get_mood(fake_redis, "u1") == 1.0
    await service.set_mood(fake_redis, "u1", -0.3)
    assert await service.get_mood(fake_redis, "u1") == 0.0


async def test_apply_emotion_positive(fake_redis):
    """正向词↑step"""
    mood = await service.apply_emotion(fake_redis, "u1", "今天好开心啊哈哈")
    assert mood > 0.5


async def test_apply_emotion_negative(fake_redis):
    """负向词↓step"""
    mood = await service.apply_emotion(fake_redis, "u1", "我好难过想哭")
    assert mood < 0.5


async def test_apply_emotion_neutral_no_change(fake_redis):
    """无情感词 mood 不变"""
    mood = await service.apply_emotion(fake_redis, "u1", "今天天气不错")
    assert mood == 0.5


async def test_seed_default_kinds(fake_redis):
    """默认 5 档种表"""
    await service.seed_default_kinds(fake_redis)
    kinds = await service.list_kinds(fake_redis)
    assert [k["key"] for k in kinds] == ["happy", "pleased", "calm", "down", "sad"]
    assert len(kinds) == 5


async def test_seed_idempotent(fake_redis):
    """种表已存在时不重复写"""
    await service.seed_default_kinds(fake_redis)
    await service.seed_default_kinds(fake_redis)
    assert len(await service.list_kinds(fake_redis)) == 5


def test_lookup_kind_boundaries():
    """档位边界查询(左闭右开,最高档含端点)"""
    kinds = service._DEFAULT_KINDS
    assert service.lookup_kind(0.8, kinds)["key"] == "happy"
    assert service.lookup_kind(0.6, kinds)["key"] == "pleased"
    assert service.lookup_kind(0.5, kinds)["key"] == "calm"
    assert service.lookup_kind(0.4, kinds)["key"] == "down"
    assert service.lookup_kind(0.2, kinds)["key"] == "sad"
    assert service.lookup_kind(1.0, kinds)["key"] == "happy"   # 最高档端点


def test_compute_mood_bias_range():
    """评分补偿 = score_bias ± noise(happy: 6 ± 3 → [3,9])"""
    kinds = service._DEFAULT_KINDS
    for _ in range(20):   # 噪声随机,多次验证范围
        bias = service.compute_mood_bias(0.8, kinds)
        assert 3 <= bias <= 9


async def test_upsert_kind_overlap_rejected(fake_redis):
    """与现有档位重叠的区间被拒(ValueError)"""
    await service.seed_default_kinds(fake_redis)
    bad = {"key": "bad", "label": "坏", "mood_lo": 0.6, "mood_hi": 0.9,
           "kaomoji": "x", "score_bias": 0, "bias_noise": 3,
           "prompt_hint": "", "color": "#000", "sort": 9}
    with pytest.raises(ValueError):
        await service.upsert_kind(fake_redis, bad)


async def test_delete_kind_keep_coverage(fake_redis):
    """删档位后若不覆盖 [0,1] 被拒"""
    await service.seed_default_kinds(fake_redis)
    # 删 sad(覆盖 0-0.3)会导致 mood=0 空档,应拒
    with pytest.raises(ValueError):
        await service.delete_kind(fake_redis, "sad")


async def test_decay_step_toward_neutral(fake_redis):
    """衰减:mood>neutral 向下 decay"""
    await service.set_mood(fake_redis, "u1", 0.8)
    await decay.decay_step(fake_redis, "u1")   # decay 0.05, neutral 0.5
    assert await service.get_mood(fake_redis, "u1") == 0.75


async def test_list_mood_objects(fake_redis):
    """set_mood 登记 oid 到 oids 集合"""
    await service.set_mood(fake_redis, "u1", 0.6)
    await service.set_mood(fake_redis, "u2", 0.4)
    assert set(await service.list_mood_objects(fake_redis)) == {"u1", "u2"}
