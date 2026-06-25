"""
测试公共夹具（fixtures）
提供 fakeredis 注入、LLM key 重置、人设临时目录、REST TestClient 等公共夹具。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：新增 fakeredis 注入夹具、LLM key 重置夹具
  2. M3.1：新增 autouse 人设临时目录夹具（防污染真实 FS）、REST TestClient 夹具
"""
import sys
from pathlib import Path

# 兜底 sys.path：让 server/app（core/llm/pipeline/storage/persona/memory）与项目根（shared）可被导入
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
    使 runner→stages→chat_store→persona/memory 全链路走内存假 Redis；测试结束还原为 None"""
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
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


@pytest.fixture(autouse=True)
def _tmp_persona_dir(tmp_path, monkeypatch):
    """自动把 persona.store 的文件双写目录重定向到临时目录，防止测试污染真实文件系统"""
    import persona.store as ps
    monkeypatch.setattr(ps, "_PERSONA_DIR", tmp_path / "persona")
    monkeypatch.setattr(ps, "_DATA_DIR", tmp_path / "data")
    yield


@pytest.fixture(autouse=True)
def _reset_memory_coordinator():
    """每个测试前重置记忆协调器单例，确保绑定当前测试的 fakeredis"""
    import memory.coordinator as mc
    mc._coordinator = None
    yield
    mc._coordinator = None


@pytest.fixture
def coord(fake_redis):
    """记忆协调器（直接构造，绑定当前 fakeredis，不走单例）"""
    from memory.coordinator import MemoryCoordinator
    return MemoryCoordinator(fake_redis)


@pytest.fixture
def client(monkeypatch, tmp_path):
    """REST 测试用 TestClient：内含独立 fakeredis，lifespan 在其 portal loop 内运行"""
    import fakeredis as _fr
    fake = _fr.FakeAsyncRedis(decode_responses=True)
    redis_client._redis = fake
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        yield c
    redis_client._redis = None
