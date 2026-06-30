"""
mood 历史曲线单测(M7):set_mood 写历史 + get_history_curve(旧→新正序)+ LTRIM 上限。
对应 docs/03 §8 实时监控 Tab 曲线。

作者: 李文煜
日期: 2026-06-30
"""
from mood import service
from core.config import settings


async def test_set_mood_records_history(fake_redis):
    """每次 set_mood 写一条历史"""
    await service.set_mood(fake_redis, "u1", 0.6)
    await service.set_mood(fake_redis, "u1", 0.8)
    curve = await service.get_history_curve(fake_redis, "u1")
    assert len(curve) == 2
    assert curve[0]["mood"] == 0.6   # 旧在前(正序)
    assert curve[1]["mood"] == 0.8


async def test_history_curve_oldest_first(fake_redis):
    """历史曲线按旧→新正序(曲线左→右)"""
    for m in (0.3, 0.5, 0.7):
        await service.set_mood(fake_redis, "u1", m)
    curve = await service.get_history_curve(fake_redis, "u1")
    assert [d["mood"] for d in curve] == [0.3, 0.5, 0.7]


async def test_history_curve_ltrim(fake_redis, monkeypatch):
    """超 mood_history_keep 的旧值被 LTRIM 裁掉"""
    monkeypatch.setattr(settings, "mood_history_keep", 3)
    for m in (0.1, 0.2, 0.3, 0.4, 0.5):
        await service.set_mood(fake_redis, "u1", m)
    curve = await service.get_history_curve(fake_redis, "u1")
    assert len(curve) == 3
    assert [d["mood"] for d in curve] == [0.3, 0.4, 0.5]   # 最近 3 条


async def test_history_curve_empty(fake_redis):
    """无 mood 记录 → 空曲线"""
    assert await service.get_history_curve(fake_redis, "u1") == []


async def test_history_entries_have_ts(fake_redis):
    """历史点带时间戳"""
    await service.set_mood(fake_redis, "u1", 0.6)
    curve = await service.get_history_curve(fake_redis, "u1")
    assert len(curve) == 1
    assert "ts" in curve[0]
