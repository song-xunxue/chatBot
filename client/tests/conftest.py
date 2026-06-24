"""
客户端测试公共夹具：sys.path 注入（client/app + 项目根 shared）、临时 SQLite 路径、
Qt offscreen QApplication 会话夹具。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建客户端测试夹具
"""
import os
import sys
from pathlib import Path

# Qt 离屏渲染（无显示器环境/CI 友好；必须在创建 QApplication 前设置）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# sys.path：client/app（模块同级导入）+ 项目根（shared）
_HERE = Path(__file__).resolve().parent            # client/tests
for _p in (str(_HERE.parent / "app"), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest


@pytest.fixture
def store(tmp_path):
    """临时 SQLite ChatStore（消息上限 5，便于测清理）"""
    from store.db import ChatStore
    s = ChatStore(tmp_path / "chat.db", message_limit=5)
    yield s
    s.close()


@pytest.fixture(scope="session")
def qapp():
    """会话级 QApplication（offscreen），供 UI 冒烟测试"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app

