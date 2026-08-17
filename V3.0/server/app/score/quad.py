"""
score 四元组计算的唯一来源(架构收口 #2,2026-07-04)
此前 score = clamp(round(score_base + mood_bias)) 散落两处:storage/chat_store.set_score(写入时算)
+ api/rest_mood.mood_calc(HTTP 试算时重算)。本 module 收口公式——改 clamp/round 约定只改一处。

mood_bias 由 mood.compute_mood_bias 产生(档位.score_bias + uniform noise);本 module 只负责
"base + bias → clamp/round → 完整四元组"的**纯计算**,不读 mood、不存库(bias 来源规则的收口归候选5)。

作者: 李文煜
日期: 2026-07-04
"""


def compute_quad(score_base: int, mood_value: float, mood_bias: float) -> dict:
    """score 四元组计算的唯一来源。
    score = clamp(round(score_base + mood_bias), 0, 100)(Python round 为银行家舍入,与原实现一致)。
    返回 {score_base, mood_at_score, mood_bias, score}。"""
    score = max(0, min(100, round(score_base + mood_bias)))
    return {"score_base": score_base, "mood_at_score": mood_value,
            "mood_bias": mood_bias, "score": score}
