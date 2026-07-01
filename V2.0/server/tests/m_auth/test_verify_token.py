"""
verify_token 鉴权依赖纯函数单测(2026-07-02,#4 鉴权去重配套)
直接对接口测(不再依赖 ASGI/TestClient 集成 round-trip)。
覆盖:Header 通过 / query 通过 / 空 token 拒 / 错 token 拒 / 服务端未配置 fail-closed。

作者: 李文煜
日期: 2026-07-02
"""
import pytest
from fastapi import HTTPException

from api._auth import verify_token
from core.config import settings


async def test_verify_token_header_ok(monkeypatch):
    """Header 带正确 token → True"""
    monkeypatch.setattr(settings, "access_token", "T")
    assert await verify_token(token="T", q_token="") is True


async def test_verify_token_query_ok(monkeypatch):
    """query 带正确 token → True(?token=T 兼容)"""
    monkeypatch.setattr(settings, "access_token", "T")
    assert await verify_token(token="", q_token="T") is True


async def test_verify_token_empty_rejected(monkeypatch):
    """空 token → 401"""
    monkeypatch.setattr(settings, "access_token", "T")
    with pytest.raises(HTTPException) as exc:
        await verify_token(token="", q_token="")
    assert exc.value.status_code == 401


async def test_verify_token_wrong_rejected(monkeypatch):
    """错 token → 401"""
    monkeypatch.setattr(settings, "access_token", "T")
    with pytest.raises(HTTPException) as exc:
        await verify_token(token="wrong", q_token="")
    assert exc.value.status_code == 401


async def test_verify_token_misconfig_fail_closed(monkeypatch):
    """服务端 access_token 未配置(空)→ fail-closed,全拒(即便 token 对也拒,防误放行)"""
    monkeypatch.setattr(settings, "access_token", "")
    with pytest.raises(HTTPException):
        await verify_token(token="anything", q_token="")
