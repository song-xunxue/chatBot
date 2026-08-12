"""
记忆遗忘机制
retain 评分(importance × recency × access × emotion 加权) + recency_decay 指数衰减。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植遗忘评分到 V2.0(零业务改动;recency_decay/retain_score/should_forget)
"""
import math
import time

from memory.models import MemoryItem, ForgetConfig


def recency_decay(last_access_ts: int, now_ts: int, half_life_hours: float) -> float:
    """间隔重复衰减:指数形式(ln2/半衰期)。
    被召回重置 last_access_ts 即重置衰减——间隔重复效应"""
    elapsed_hours = max(0.0, (now_ts - last_access_ts) / 3_600_000.0)
    return math.exp(-0.693 * elapsed_hours / half_life_hours)


def retain_score(item: MemoryItem, cfg: ForgetConfig, now_ts: int = 0) -> float:
    """保留分:w1*importance + w2*recency + w3*log1p(access) + w4*emotion"""
    now_ts = now_ts or int(time.time() * 1000)
    return (
        cfg.w_importance * item.importance
        + cfg.w_recency * recency_decay(item.last_access_ts, now_ts, cfg.decay_half_life_hours)
        + cfg.w_access * math.log1p(item.access_count)
        + cfg.w_emotion * item.emotion
    )


def _auto_tier(item: MemoryItem, cfg: ForgetConfig) -> int:
    """2026-08-13 自动档判定(tier==-1 时由 useful_score 推档):
    useful_score >= tier1_threshold → T2(永不);>= tier0_threshold → T1(评分驱动);否则 T0(自然衰减)。"""
    if item.useful_score >= cfg.tier1_threshold:
        return 2
    if item.useful_score >= cfg.tier0_threshold:
        return 1
    return 0


def should_forget(item: MemoryItem, cfg: ForgetConfig, now_ts: int = 0) -> bool:
    """是否应遗忘(2026-08-13 三档衰减):
    - forgotten→True;locked→False(手动锁,强制永不)
    - tier>=0 用手动档;tier==-1 由 useful_score 自动判档(_auto_tier)
    - T2(永不)→False;T1(评分驱动)→useful_score 跌破 tier0_threshold 才忘;T0(自然衰减)→retain_score 跌破阈值才忘"""
    if item.forgotten:
        return True
    if item.locked:
        return False
    tier = item.tier if item.tier >= 0 else _auto_tier(item, cfg)
    if tier == 2:
        return False
    if tier == 1:
        # T1:只在 useful_score 跌破 T0 阈值时才忘(评分驱动的用进废退)
        return item.useful_score < cfg.tier0_threshold
    # T0:自然衰减(原 retain_score 逻辑)
    return retain_score(item, cfg, now_ts) < cfg.retain_threshold
