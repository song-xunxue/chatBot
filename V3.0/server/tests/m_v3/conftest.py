"""
V3.0 适配器/OneBot 测试公共夹具(仿 m4/conftest)。

作者: 李文煜
日期: 2026-08-16
"""
import pytest
import fakeredis


@pytest.fixture
def fake_redis():
    """独立 fakeredis 实例(decode_responses=True)"""
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield fake
