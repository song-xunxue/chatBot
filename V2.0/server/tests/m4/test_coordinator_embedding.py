"""
coordinator 向量重排 + 语义去重单测(2026-07-07 记忆优化阶段1):
1. 无 embedding provider → retrieve 降级纯 BM25 不报错
2. 配置 provider → 新记忆写入同步存 vec
3. 语义去重:相同内容(cosine=1>=阈值)→ 合并 access_count++,不新建

作者: 李文煜
日期: 2026-07-07
"""
import pytest

from memory import coordinator as coord_mod
from memory.coordinator import MemoryCoordinator


class _FakeEmbedding:
    """确定性 mock embedding:同文本 → 同向量(供去重测试);不同文本 → 不同向量。
    不做真实语义,只验证调用链路与去重逻辑。"""

    def __init__(self):
        self.calls = 0

    async def embed(self, texts, model=""):
        self.calls += 1
        out = []
        for t in texts:
            # 同文本得同向量(hash 确定性);向量首位=内容标识,其余位固定
            h = abs(hash(t)) % 97
            out.append([float(h), 0.5, 0.3])
        return out


def _patch_provider(monkeypatch, provider):
    """patch llm.embedding.get_embedding_provider 返回指定 provider(None=禁用)"""
    monkeypatch.setattr("llm.embedding.get_embedding_provider", lambda name="": provider)


@pytest.fixture
def coord(fake_redis):
    return MemoryCoordinator(redis=fake_redis, llm_provider=None)


async def test_retrieve_no_provider_falls_back_bm25(monkeypatch, fake_redis):
    """优化1:无 embedding provider 时 retrieve 走 BM25 不报错"""
    _patch_provider(monkeypatch, None)
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.8,
                                      "emotion": 0.5, "category": "preference"})
    # retrieve 不应抛异常(BM25 降级)
    result = await c.retrieve("u1", "动漫")
    assert result.long_term is not None   # 至少返回(可能空但有字段)


async def test_upsert_stores_vec_when_provider_configured(monkeypatch, fake_redis):
    """优化1:配置 provider 时,新记忆写入同步存 vec"""
    fake = _FakeEmbedding()
    _patch_provider(monkeypatch, fake)
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.8,
                                      "emotion": 0.5, "category": "preference"})
    items = await __import__("memory.store", fromlist=["get_all_long_term"]).get_all_long_term(fake_redis, "u1")
    assert len(items) == 1
    from memory import store
    vec = await store.get_vec(fake_redis, "u1", items[0].id)
    assert vec is not None and len(vec) == 3   # _FakeEmbedding 产出 3 维


async def test_upsert_semantic_dedup_same_content_merges(monkeypatch, fake_redis):
    """优化2:相同内容(cosine=1>=0.85)→ 合并 access_count++,不新建第二条"""
    fake = _FakeEmbedding()
    _patch_provider(monkeypatch, fake)
    c = MemoryCoordinator(redis=fake_redis, llm_provider=None)
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.8,
                                      "emotion": 0.5, "category": "preference"})
    await c._upsert_fact_dedup("u1", {"content": "用户喜欢动漫", "importance": 0.9,
                                      "emotion": 0.6, "category": "preference"})
    from memory import store
    items = await store.get_all_long_term(fake_redis, "u1")
    assert len(items) == 1               # 去重,未新建
    assert items[0].access_count == 1    # 合并:第二次命中去重,access_count 从 0 → 1
    assert items[0].importance == 0.9    # importance 取 max
