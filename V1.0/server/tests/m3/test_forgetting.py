"""
记忆遗忘机制单元测试
验证 recency_decay 衰减/重置、retain_score 公式、should_forget 阈值/locked/forgotten

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.5 覆盖 forgetting 全部函数
"""
import math

from memory.forgetting import recency_decay, retain_score, should_forget
from memory.models import MemoryItem, ForgetConfig


def test_recency_decay_now_is_one():
    assert recency_decay(0, 0, 72.0) == 1.0  # 0 elapsed → 1.0


def test_recency_decay_half_life():
    # 一个半衰期后 → 0.5
    b = recency_decay(0, 72 * 3_600_000, 72.0)
    assert abs(b - 0.5) < 0.01


def test_recency_decay_resets_on_recent_access():
    now = 10_000_000
    recent = recency_decay(now - 1000, now, 72.0)   # 刚访问
    old = recency_decay(0, now, 72.0)               # 很久前
    assert recent > old


def test_retain_score_formula():
    item = MemoryItem(id="m", content="x", importance=0.8, emotion=0.6,
                      access_count=3, last_access_ts=0)
    cfg = ForgetConfig()
    score = retain_score(item, cfg, now_ts=0)
    expected = (0.4 * 0.8 + 0.3 * 1.0 + 0.15 * math.log1p(3) + 0.15 * 0.6)
    assert abs(score - expected) < 0.001


def test_should_forget_below_threshold():
    # 低 importance/emotion/access，很久未访问 → 跌破
    # 注意：last_access_ts 传非 0 小值，避免 __post_init__ 填成当前时间戳
    item = MemoryItem(id="m", content="x", importance=0.1, emotion=0.0,
                      access_count=0, created_ts=1, last_access_ts=1)
    cfg = ForgetConfig(retain_threshold=0.3)
    assert should_forget(item, cfg, now_ts=100 * 3_600_000) is True


def test_should_forget_keeps_important():
    item = MemoryItem(id="m", content="x", importance=0.9, emotion=0.0,
                      access_count=0, created_ts=1, last_access_ts=1)
    cfg = ForgetConfig(retain_threshold=0.3)
    # retain ≈ 0.4*0.9 + 衰减项 > 0.3
    assert should_forget(item, cfg, now_ts=100 * 3_600_000) is False


def test_should_forget_locked_never():
    item = MemoryItem(id="m", content="x", importance=0.0, locked=True)
    assert should_forget(item, ForgetConfig(retain_threshold=0.9), now_ts=999) is False


def test_should_forget_already_forgotten():
    item = MemoryItem(id="m", content="x", forgotten=True)
    assert should_forget(item, ForgetConfig()) is True
