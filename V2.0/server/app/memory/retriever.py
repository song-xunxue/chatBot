"""
记忆检索器
Retriever 抽象(rank 打分)+ KeywordRetriever(关键词交集)+ BM25Retriever(BM25 评分,
M4 借鉴 angel_memory 三层检索的零依赖落地)+ EmbeddingRetriever(占位,M5 向量库)+
sample_weighted(加权随机召回,避确定性偏见,angel_memory 借鉴)。

M4 改造:检索器只负责 rank(返回 (score,item) 降序),top-K 截断交给 coordinator
(确定性 or 加权随机),便于在召回层引入多样性。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植检索器到 V2.0(零业务改动;KeywordRetriever 零依赖分词召回)

2026-06-28
变更说明：
  1. M4 重构:Retriever 抽象改为 rank() 打分 + retrieve() 默认实现(rank+确定性 topK);
     新增 BM25Retriever(BM25 评分替交集计数,零依赖);新增 sample_weighted(加权随机召回)
"""
import math
import random
import re
from abc import ABC, abstractmethod
from collections import Counter

from memory.models import MemoryItem


def _tokenize(text: str) -> list[str]:
    """简易分词:中文按单字、英文/数字按词,去标点并小写(零依赖,无需 jieba)。
    返回 list(保留词频供 BM25 TF 统计;去重用 set() 包一下即可)"""
    if not text:
        return []
    return re.findall(r"[一-龥]|[a-zA-Z0-9]+", text.lower())


class Retriever(ABC):
    """检索器抽象:从候选长期记忆中按 query 打分排序(rank),top-K 截断交 coordinator"""

    @abstractmethod
    def rank(self, candidates: list[MemoryItem], query: str) -> list[tuple[float, MemoryItem]]:
        """打分排序:返回 (score, item) 降序列表(仅 score>0 的候选)"""
        ...

    def retrieve(self, candidates: list[MemoryItem], query: str,
                 top_k: int) -> tuple[list[MemoryItem], list[str]]:
        """确定性 top-K 截断(兼容旧接口;coordinator M4 起改用 rank + sample_weighted)"""
        ranked = self.rank(candidates, query)
        hits = [m for _, m in ranked[:top_k]]
        return hits, [m.id for m in hits]


class KeywordRetriever(Retriever):
    """关键词召回:query 与记忆 content 的 token 交集数评分(首版零依赖)"""

    def rank(self, candidates: list[MemoryItem], query: str) -> list[tuple[float, MemoryItem]]:
        if not candidates:
            return []
        q_tokens = set(_tokenize(query))
        if not q_tokens:
            return []
        scored: list[tuple[float, MemoryItem]] = []
        for m in candidates:
            overlap = len(q_tokens & set(_tokenize(m.content)))
            if overlap > 0:
                scored.append((float(overlap), m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored


class BM25Retriever(Retriever):
    """BM25 召回(M4,借鉴 angel_memory 三层检索的零依赖落地):
    IDF×TF 评分替纯交集计数,稀有词(rare term)命中权重更高,区分度更好。
    公式:score = Σ IDF(q) · TF(q,d)·(k1+1) / (TF(q,d) + k1·(1-b+b·|d|/avgdl))
    零依赖(无外部 BM25 库),中文按字/英文按词(_tokenize)。"""

    k1 = 1.5   # TF 饱和参数
    b = 0.75   # 文档长度归一化参数

    def rank(self, candidates: list[MemoryItem], query: str) -> list[tuple[float, MemoryItem]]:
        if not candidates:
            return []
        q_tokens = set(_tokenize(query))
        if not q_tokens:
            return []
        docs = [_tokenize(m.content) for m in candidates]
        n = len(docs)
        avgdl = (sum(len(d) for d in docs) / n) if n else 0.0
        # df:每个 token 出现在多少篇文档(供 IDF)
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        scored: list[tuple[float, MemoryItem]] = []
        for m, d in zip(candidates, docs):
            if not d:
                continue
            tf = Counter(d)
            dl = len(d)
            score = 0.0
            for t in q_tokens:
                if t not in tf:
                    continue
                # IDF(下界钳制非负):log((N - df + 0.5)/(df + 0.5) + 1)
                idf = math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1)
                denom = tf[t] * (self.k1 + 1)
                norm = tf[t] + self.k1 * (1 - self.b + self.b * dl / (avgdl or 1.0))
                score += idf * (denom / norm) if norm else 0.0
            if score > 0:
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored


class EmbeddingRetriever(Retriever):
    """向量语义检索(占位,M5 实现,需向量库或 embedding API)"""

    def rank(self, candidates: list[MemoryItem], query: str) -> list[tuple[float, MemoryItem]]:
        raise NotImplementedError("EmbeddingRetriever 待 M5 实现(需向量索引/embedding API)")


def sample_weighted(ranked: list[tuple[float, MemoryItem]], top_k: int,
                    temperature: float = 1.0) -> list[MemoryItem]:
    """加权随机召回(angel_memory 借鉴):按 score softmax 加权无放回采样 top_k。
    高分高概率,但每次召回略有变化,避免确定性偏见(每次都召回相同条目)。
    候选数 <= top_k 时全取(无需采样)。temperature 越大随机性越强。"""
    if len(ranked) <= top_k:
        return [m for _, m in ranked]
    scores = [max(s, 0.0) for s, _ in ranked]
    mx = max(scores) if scores else 0.0
    weights = [math.exp((s - mx) / max(temperature, 1e-6)) for s in scores]
    # 加权无放回采样:每轮按剩余权重抽一个
    pool = list(range(len(ranked)))
    chosen: list[int] = []
    for _ in range(top_k):
        if not pool:
            break
        ws = [weights[i] for i in pool]
        total = sum(ws) or 1.0
        r = random.random() * total
        acc = 0.0
        picked = pool[-1]
        for idx, i in enumerate(pool):
            acc += ws[idx]
            if r <= acc:
                picked = i
                pool.pop(idx)
                break
        else:
            pool.remove(picked)
        chosen.append(picked)
    chosen.sort()   # 按原 rank 顺序输出(稳定注入顺序)
    return [ranked[i][1] for i in chosen]
