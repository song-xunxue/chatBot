"""
M6 测试公共夹具:fakeredis + EventBus + ToolRegistry。
自举:把 plugins/star_compat/ 加入 sys.path,使测试可 `import astrbot`(命中兼容包)。

作者: 李文煜
日期: 2026-06-28
"""
import sys
from pathlib import Path

import pytest
import fakeredis

# 自举:star_compat/ 加入 sys.path(import astrbot 命中 V2.0 兼容包,非真 AstrBot)
_COMPAT = Path(__file__).resolve().parents[2] / "app" / "plugins" / "star_compat"
if str(_COMPAT) not in sys.path:
    sys.path.insert(0, str(_COMPAT))


@pytest.fixture
def fake_redis():
    yield fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def bus():
    from plugins.event import EventBus
    return EventBus()


@pytest.fixture
def tool_registry():
    from tools.base import ToolRegistry
    return ToolRegistry()
