"""
mood 全局参数 Redis 存储单测(M7):get_params/set_params + apply_emotion/decay 改读 Redis。
对应 docs/03 §8 全局参数 Tab。

作者: 李文煜
日期: 2026-06-30
"""
import pytest

from mood import service, decay
from core.config import settings


async def test_get_params_fallback_settings(fake_redis):
    """未配置时所有参数回退 settings 同名字段"""
    params = await service.get_params(fake_redis)
    assert params["mood_step"] == settings.mood_step
    assert params["mood_decay"] == settings.mood_decay
    assert params["mood_neutral"] == settings.mood_neutral
    assert params["mood_kaomoji_prob"] == settings.mood_kaomoji_prob


async def test_set_params_then_get(fake_redis):
    """set 后 get 读到 Redis 新值;未改的字段仍回退 settings"""
    await service.set_params(fake_redis, {"mood_step": 0.2, "mood_decay": 0.08})
    params = await service.get_params(fake_redis)
    assert params["mood_step"] == 0.2
    assert params["mood_decay"] == 0.08
    assert params["mood_neutral"] == settings.mood_neutral   # 未改 → 回退


async def test_set_params_reject_out_of_range(fake_redis):
    """参数超 [0,1] 被拒(ValueError)"""
    with pytest.raises(ValueError):
        await service.set_params(fake_redis, {"mood_step": 1.5})
    with pytest.raises(ValueError):
        await service.set_params(fake_redis, {"mood_neutral": -0.1})


async def test_apply_emotion_uses_redis_param(fake_redis):
    """apply_emotion 读 Redis mood_step(改大 → 情感步长变大)"""
    await service.set_params(fake_redis, {"mood_step": 0.3})
    mood = await service.apply_emotion(fake_redis, "u1", "今天好开心哈哈")   # 正向词,+step
    assert mood == pytest.approx(0.8)   # 0.5 + 0.3


async def test_decay_uses_redis_param(fake_redis):
    """decay_step 读 Redis mood_decay/neutral(改衰减幅度 → 衰减变化)"""
    await service.set_mood(fake_redis, "u1", 0.8)
    await service.set_params(fake_redis, {"mood_decay": 0.1, "mood_neutral": 0.5})
    await decay.decay_step(fake_redis, "u1")
    assert await service.get_mood(fake_redis, "u1") == 0.7   # 0.8 - 0.1
