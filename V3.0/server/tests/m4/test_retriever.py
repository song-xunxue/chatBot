"""
retriever 单测(M4):BM25 评分(稀有词高分)/ KeywordRetriever / sample_weighted
(全取/采样数量/高分偏向)。

作者: 李文煜
日期: 2026-06-28

2026-06-28
变更说明:
  1. M4 创建 retriever 单测(BM25 稀有词/TF 排序/KeywordRetriever/sample_weighted 三性质)
"""
from memory.models import MemoryItem
from memory.retriever import KeywordRetriever, BM25Retriever, sample_weighted


def _m(content: str, mid: str = "m") -> MemoryItem:
    return MemoryItem(id=mid, content=content)


def test_bm25_rare_term_hits_only_matching():
    """BM25:含 query 词的候选命中,不含的不入列"""
    cands = [_m("我喜欢的动物", "m1"), _m("猫是可爱的动物", "m2"), _m("狗和鸟", "m3")]
    ranked = BM25Retriever().rank(cands, "猫")
    ids = [m.id for _, m in ranked]
    assert ids == ["m2"]   # 只有 m2 含"猫"


def test_bm25_higher_tf_ranks_first():
    """BM25:TF 高的(词频多)排在前面"""
    cands = [_m("猫猫猫", "a"), _m("猫", "b")]
    ranked = BM25Retriever().rank(cands, "猫")
    assert ranked[0][1].id == "a"   # 猫猫猫 TF=3 > 猫 TF=1


def test_bm25_score_positive_and_descending():
    """BM25:返回分数 >0 且降序"""
    cands = [_m("猫狗"), _m("猫猫"), _m("猫")]
    ranked = BM25Retriever().rank(cands, "猫")
    assert all(s > 0 for s, _ in ranked)
    scores = [s for s, _ in ranked]
    assert scores == sorted(scores, reverse=True)


def test_bm25_empty_query_or_candidates():
    assert BM25Retriever().rank([], "猫") == []
    assert BM25Retriever().rank([_m("猫")], "") == []


def test_keyword_retriever_overlap_count():
    """KeywordRetriever:交集数评分"""
    ranked = KeywordRetriever().rank([_m("猫狗鱼", "a"), _m("猫", "b"), _m("鸟", "c")], "猫狗")
    ids = [m.id for _, m in ranked]
    assert ids[0] == "a"   # 交集 2 最多
    assert "c" not in ids  # 无交集


def test_sample_weighted_all_when_few():
    """候选 <= top_k:全取(不采样)"""
    ranked = [(1.0, _m("a", "a")), (2.0, _m("b", "b"))]
    assert {m.id for m in sample_weighted(ranked, 5)} == {"a", "b"}


def test_sample_weighted_returns_topk_unique():
    """候选 > top_k:采样返回恰好 top_k 个、不重复"""
    ranked = [(float(i), _m(f"m{i}", f"m{i}")) for i in range(10)]
    out = sample_weighted(ranked, 3)
    assert len(out) == 3
    assert len({m.id for m in out}) == 3   # 无放回,不重复


def test_sample_weighted_biased_to_high_score():
    """加权随机:高分条目被采中频率显著高于低分(统计性,softmax 温度 1)"""
    ranked = [(10.0, _m("hi", "hi")), (0.0, _m("lo", "lo"))]
    hi = sum(1 for _ in range(60) if sample_weighted(ranked, 1)[0].id == "hi")
    assert hi > 40   # 高分(e^10 优势)应绝大多数时候被采中
