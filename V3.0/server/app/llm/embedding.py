"""
Embedding Provider —— 向量语义检索用(2026-07-07 记忆优化:激活向量检索 + 语义去重)。
GLM(智谱)提供 OpenAI 兼容 /embeddings 接口;失败/无 key 时调用方降级(纯 BM25,不影响现有)。

作者: 李文煜
日期: 2026-07-07

2026-07-07
变更说明：
  1. 记忆优化阶段1:新建 embedding provider(GLM embedding-3,OpenAI 兼容),
     供记忆向量检索(BM25+向量 RRF 融合)与语义去重(cosine 替 Jaccard)
"""
import logging
from abc import ABC, abstractmethod

import httpx  # 异步 HTTP 客户端(复用 openai_compat 的调用模式)

from core.config import settings

logger = logging.getLogger(__name__)

# 单批 input 条数上限(智谱文档限制 64,保守取 32 避超限;超出分批 POST)
_BATCH = 32


class EmbeddingProvider(ABC):
    """Embedding 抽象:批量文本 → 向量列表(顺序对齐输入)。子类对接具体厂商。"""

    name: str = ""

    @abstractmethod
    async def embed(self, texts: list[str], model: str = "") -> list[list[float]]:
        """批量嵌入;返回与 texts 等长、顺序对齐的向量列表"""
        ...


class GLMEmbedding(EmbeddingProvider):
    """GLM(智谱)embedding —— OpenAI 兼容 /embeddings 端点(与 GLMProvider 同 base_url)。
    embedding-3 默认 2048 维(可 dimensions 参数调 512/1024/2048)。"""

    name = "glm"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    default_model = "embedding-3"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    @property
    def _headers(self) -> dict:
        # OpenAI 兼容鉴权:Bearer token
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def embed(self, texts: list[str], model: str = "") -> list[list[float]]:
        """批量嵌入:分批 POST /embeddings,返回顺序对齐的向量列表。失败抛异常(调用方降级)"""
        model = model or self.default_model
        if not texts:
            return []
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=60) as client:
            # 分批(input 数组上限),逐批 POST 累积结果
            for i in range(0, len(texts), _BATCH):
                batch = texts[i:i + _BATCH]
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=self._headers,
                    json={"model": model, "input": batch},
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                # 按 index 排序确保顺序与输入对齐(厂商一般已有序,防御性排序)
                data.sort(key=lambda d: d.get("index", 0))
                out.extend(d["embedding"] for d in data)
        return out


def get_embedding_provider(name: str = "") -> EmbeddingProvider | None:
    """按 name 实例化 embedding provider;未配置/无 key 返回 None(调用方降级纯 BM25)。
    默认从 settings.memory_embedding_provider 读。目前支持 glm;后续可扩展 siliconflow/openai。"""
    name = (name or getattr(settings, "memory_embedding_provider", "") or "").lower()
    if name == "glm":
        if not settings.glm_api_key:
            logger.warning("memory_embedding_provider=glm 但 glm_api_key 未配置,降级纯 BM25")
            return None
        return GLMEmbedding(api_key=settings.glm_api_key)
    return None
