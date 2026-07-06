"""
向量检索工具单测(2026-07-07 记忆优化阶段1):cosine_similarity + rrf_fuse 纯函数。

作者: 李文煜
日期: 2026-07-07
"""
from memory.retriever import cosine_similarity, rrf_fuse
from memory.models import MemoryItem


def test_cosine_similarity_basic():
    """cosine:相同=1,正交=0,反向=-1,零向量=0"""
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0   # 零向量防除零


def test_rrf_fuse_merges_and_ranks_cross_list():
    """RRF:两路 rank 融合;两路都高排名的应排最前(跨路命中加分)"""
    m1, m2, m3 = (MemoryItem(id="m1", content="a"),
                  MemoryItem(id="m2", content="b"),
                  MemoryItem(id="m3", content="c"))
    ranked_a = [(1.0, m1), (0.5, m2)]      # BM25 路:m1 > m2
    ranked_b = [(0.9, m2), (0.3, m3)]      # 向量路:m2 > m3
    fused = rrf_fuse(ranked_a, ranked_b)
    ids = [m.id for _, m in fused]
    assert set(ids) == {"m1", "m2", "m3"}
    # m2 在两路都靠前(rank1 + rank0),融合分最高
    assert fused[0][1].id == "m2"


def test_rrf_fuse_single_list_preserved():
    """RRF:某路为空时,另一路原序保留(单路命中不丢)"""
    m1, m2 = MemoryItem(id="m1", content="a"), MemoryItem(id="m2", content="b")
    ranked_a = [(1.0, m1), (0.5, m2)]
    fused = rrf_fuse(ranked_a, [])
    assert [m.id for _, m in fused] == ["m1", "m2"]
