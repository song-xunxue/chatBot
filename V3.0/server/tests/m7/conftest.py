"""
M7 测试公共夹具:EventBus + ToolRegistry(star_reload 测试用)。
自举:把 plugins/star_compat/ 加入 sys.path,使测试可 `import astrbot`(命中 V2.0 兼容包)。
fake_redis 沿用根 conftest(注入 redis_client._redis)。

作者: 李文煜
日期: 2026-06-30
"""
import sys
from pathlib import Path

import pytest

# 自举:star_compat/ 加入 sys.path(import astrbot 命中 V2.0 兼容包,非真 AstrBot)
_COMPAT = Path(__file__).resolve().parents[2] / "app" / "plugins" / "star_compat"
if str(_COMPAT) not in sys.path:
    sys.path.insert(0, str(_COMPAT))


@pytest.fixture
def bus():
    """独立 EventBus(star_loader 适配测试用)"""
    from plugins.event import EventBus
    return EventBus()


@pytest.fixture
def tool_registry():
    """独立 ToolRegistry(star_loader @llm_tool 适配测试用)"""
    from tools.base import ToolRegistry
    return ToolRegistry()
