"""
m_wb(世界书)测试公共夹具:coordinator 单例复位。
注入的向量兜底(worldbook_runtime._topup_from_retriever)会经 get_memory_coordinator()
建真单例,测试后不复位会携带 fakeredis 句柄泄漏到其它测试组。

日期: 2026-10-26
"""
import pytest


@pytest.fixture(autouse=True)
def _reset_coord():
    """每个用例前后复位记忆协调器单例(防跨测试泄漏)"""
    from memory.coordinator import reset_coordinator
    reset_coordinator()
    yield
    reset_coordinator()
