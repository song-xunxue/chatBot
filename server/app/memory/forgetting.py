"""
记忆遗忘机制
retain 评分（importance × recency × access × emotion 加权）+ recency_decay 指数衰减。
对应 docs/06 §6、docs/09 §2.4。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.5 创建遗忘评分：recency_decay/retain_score/should_forget
"""
import math
import time

from memory.models import MemoryItem, ForgetConfig


def recency_decay(last_access_ts: int, now_ts: int, half_life_hours: float) -> float:
    """间隔重复衰减：指数形式（ln2/半衰期）。
    被召回重置 last_access_ts 即重置衰减——对应 docs/06 §6.1 间隔重复效应"""
    elapsed_hours = max(0.0, (now_ts - last_access_ts) / 3_600_000.0)
    return math.exp(-0.693 * elapsed_hours / half_life_hours)


def retain_score(item: MemoryItem, cfg: ForgetConfig, now_ts: int = 0) -> float:
    """保留分：w1*importance + w2*recency + w3*log1p(access) + w4*emotion"""
    now_ts = now_ts or int(time.time() * 1000)
    return (
        cfg.w_importance * item.importance
        + cfg.w_recency * recency_decay(item.last_access_ts, now_ts, cfg.decay_half_life_hours)
        + cfg.w_access * math.log1p(item.access_count)
        + cfg.w_emotion * item.emotion
    )


def should_forget(item: MemoryItem, cfg: ForgetConfig, now_ts: int = 0) -> bool:
    """是否应遗忘：已 forgotten→True；locked→False（锁定防遗忘）；否则 retain 跌破阈值→True"""
    if item.forgotten:
        return True
    if item.locked:
        return False
    return retain_score(item, cfg, now_ts) < cfg.retain_threshold
