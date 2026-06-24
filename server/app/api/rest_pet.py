"""
桌宠外观 REST：上传 / 获取 / 删除桌宠头像（图标）。
存储 server/data/pet/avatar.<ext>，Redis 记录扩展名；GET 返回图像文件供客户端渲染。
客户端优先用上传的头像，否则用内置默认外观（fox.svg）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.1 创建桌宠头像接口：upload/get/delete
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from core.config import PROJECT_ROOT, settings
from storage.redis_client import get_redis

router = APIRouter(prefix="/api/v1", tags=["pet"])

# 桌宠头像存储目录（模块级变量，便于测试 monkeypatch 到临时目录）
_PET_DIR: Path = PROJECT_ROOT / "server" / "data" / "pet"
_K_EXT = "mychat:pet:avatar_ext"                       # Redis：记录当前头像扩展名
_ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
_MAX_BYTES = 2 * 1024 * 1024                           # 2MB 上限


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖：Header 或 query 任一通过；显式拒绝空 token"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


@router.post("/pet/avatar", dependencies=[Depends(_auth)])
async def upload_pet_avatar(file: UploadFile = File(...)):
    """上传/替换桌宠头像（覆盖旧文件）"""
    ext = (file.filename or "png").rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {ext}，允许: {sorted(_ALLOWED_EXT)}")
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="头像过大(>2MB)")
    _PET_DIR.mkdir(parents=True, exist_ok=True)
    for f in _PET_DIR.glob("avatar.*"):                 # 清旧（避免残留多扩展名文件）
        f.unlink()
    path = _PET_DIR / f"avatar.{ext}"
    path.write_bytes(data)
    redis = await get_redis()
    await redis.set(_K_EXT, ext)
    return {"avatar": str(path)}


@router.get("/pet/avatar", dependencies=[Depends(_auth)])
async def get_pet_avatar():
    """获取当前桌宠头像（图像文件）；未上传返回 404，客户端回退默认外观"""
    redis = await get_redis()
    ext = await redis.get(_K_EXT)
    if not ext:
        raise HTTPException(status_code=404, detail="no pet avatar")
    path = _PET_DIR / f"avatar.{ext}"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no pet avatar")
    return FileResponse(str(path))


@router.delete("/pet/avatar", dependencies=[Depends(_auth)])
async def delete_pet_avatar():
    """删除桌宠头像（恢复默认外观）"""
    redis = await get_redis()
    ext = await redis.get(_K_EXT)
    removed = False
    if ext:
        path = _PET_DIR / f"avatar.{ext}"
        if path.is_file():
            path.unlink()
            removed = True
    await redis.delete(_K_EXT)
    return {"deleted": removed}
