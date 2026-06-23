"""
记忆检索器
Retriever 抽象基类 + KeywordRetriever（首版，关键词召回 top-K）+ EmbeddingRetriever（占位，M4/M5）。
对应 docs/06 §5、docs/09 §4.1。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.3 创建检索器抽象 + KeywordRetriever 关键词召回
"""
import re
from abc import ABC, abstractmethod

from memory.models import MemoryItem


def _tokenize(text: str) -> set[str]:
    """简易分词：中文按单字、英文/数字按词，去标点并小写（零依赖，无需 jieba）"""
    if not text:
        return set()
    return set(re.findall(r"[一-龥]|[a-zA-Z0-9]+", text.lower()))


class Retriever(ABC):
    """检索器抽象：从候选长期记忆中按 query 召回 top-K"""

    @abstractmethod
    def retrieve(self, candidates: list[MemoryItem], query: str,
                 top_k: int) -> tuple[list[MemoryItem], list[str]]:
        """返回 (命中记忆列表, 命中 mid 列表)"""
        ...


class KeywordRetriever(Retriever):
    """关键词召回：query 与记忆 content 的 token 交集评分，按交集数降序取 top-K"""

    def retrieve(self, candidates: list[MemoryItem], query: str,
                 top_k: int) -> tuple[list[MemoryItem], list[str]]:
        if not candidates:
            return [], []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return [], []
        scored: list[tuple[int, MemoryItem]] = []
        for m in candidates:
            overlap = len(q_tokens & _tokenize(m.content))
            if overlap > 0:  # 仅保留有交集的
                scored.append((overlap, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = [m for _, m in scored[:top_k]]
        return hits, [m.id for m in hits]


class EmbeddingRetriever(Retriever):
    """向量语义检索（占位，M4/M5 实现，需向量库或 embedding API）"""

    def retrieve(self, candidates: list[MemoryItem], query: str,
                 top_k: int) -> tuple[list[MemoryItem], list[str]]:
        raise NotImplementedError("EmbeddingRetriever 待 M4/M5 实现（需向量索引）")
