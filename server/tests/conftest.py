"""
测试公共夹具（fixtures）
提供 fakeredis 注入、LLM key 重置等公共夹具，供各测试模块复用

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：新增 fakeredis 注入夹具（替代真实 Redis）、LLM key 重置夹具
"""
import sys
from pathlib import Path

# 兜底 sys.path：让 server/app（core/llm/pipeline/storage）与项目根（shared）可被导入
_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parent / "app"), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
import fakeredis

import storage.redis_client as redis_client
from core.config import settings


@pytest.fixture
def fake_redis():
    """注入 fakeredis 单例到 storage.redis_client._redis
    使 runner→stages→chat_store 全链路走内存假 Redis；测试结束还原为 None"""
    fake = fakeredis.FakeAsyncRedis()
    redis_client._redis = fake
    yield fake
    redis_client._redis = None


@pytest.fixture
def reset_llm_keys(monkeypatch):
    """清空所有 LLM api_key，测试 available_providers 的有/无 key 分支
    monkeypatch 会在测试结束自动还原回 .env 真实值"""
    monkeypatch.setattr(settings, "glm_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
