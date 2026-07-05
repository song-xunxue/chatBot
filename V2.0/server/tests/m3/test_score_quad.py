"""
score.quad compute_quad 单测(架构 #2 收口):公式 clamp(round(base+bias)) 的唯一来源。
钉死:基础相加 / 上下界 clamp / 银行家 round / 返回四元组完整键。

作者: 李文煜
日期: 2026-07-04
"""
from score.quad import compute_quad


def test_quad_basic():
    q = compute_quad(80, 0.7, 2.0)
    assert q["score"] == 82
    assert q["score_base"] == 80 and q["mood_at_score"] == 0.7 and q["mood_bias"] == 2.0


def test_quad_clamp_low():
    assert compute_quad(5, 0.3, -20)["score"] == 0


def test_quad_clamp_high():
    assert compute_quad(95, 0.9, 20)["score"] == 100


def test_quad_round():
    assert compute_quad(80, 0.5, 2.6)["score"] == 83   # 82.6 → 83
    assert compute_quad(80, 0.5, 2.4)["score"] == 82   # 82.4 → 82


def test_quad_returns_full_dict_keys():
    q = compute_quad(70, 0.6, 1.0)
    assert set(q.keys()) == {"score_base", "mood_at_score", "mood_bias", "score"}


def test_quad_negative_bias_can_lower_score():
    # mood_bias 可为负(低心情档位),拉低 score
    assert compute_quad(60, 0.2, -5)["score"] == 55
