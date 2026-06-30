"""
REST 鉴权公共依赖(M7)
抽各 router 重复的 _auth(X-Access-Token Header 或 ?token= query,对 settings.access_token 校验)。
M7 新 router 经 Depends(verify_token) 复用;rest_score/rest_memory 保留各自 _auth(M3/M4 已测,不改)。

作者: 李文煜
日期: 2026-06-30
"""
from fastapi import Header, HTTPException, Query

from core.config import settings


async def verify_token(token: str = Header(default="", alias="X-Access-Token"),
                       q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖:Header 或 query 任一通过;显式拒绝空/错 token(与 rest_score/rest_memory 一致)。
    失败抛 401。"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True
