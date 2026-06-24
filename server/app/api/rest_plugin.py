"""
插件 REST 接口
插件列表/详情、全局开关 enable/disable、按对象配置 GET/PUT、reload。
复用 access_token 鉴权（Header X-Access-Token 或 query token）。对应 docs/05 §9。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.2 创建插件配置 REST 接口
"""
from fastapi import APIRouter, HTTPException, Header, Query, Depends

from storage.redis_client import get_redis
from core.config import settings
from plugins import get_plugin_manager

router = APIRouter(prefix="/api/v1", tags=["plugin"])


async def _auth(token: str = Header(default="", alias="X-Access-Token"),
                q_token: str = Query(default="", alias="token")):
    """access_token 鉴权依赖：Header 或 query 任一通过即可；显式拒绝空 token（防误配开放）"""
    supplied = token or q_token
    if not settings.access_token or not supplied or supplied != settings.access_token:
        raise HTTPException(status_code=401, detail="invalid access token")
    return True


def _require_manager():
    """取插件管理器；未初始化（plugin_enabled=False 或 lifespan 未跑）返回 503"""
    mgr = get_plugin_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="plugin system not initialized")
    return mgr


@router.get("/plugin", dependencies=[Depends(_auth)])
async def list_plugins():
    """列出所有已加载插件（含 manifest 摘要 + 全局开关状态）"""
    mgr = _require_manager()
    out = []
    for name in mgr.list_loaded():
        mf = mgr.get_manifest(name)
        out.append({
            **mgr.manifest_to_dict(mf),
            "global_enabled": await mgr.get_global_enabled(name),
        })
    return out


@router.get("/plugin/{name}", dependencies=[Depends(_auth)])
async def get_plugin(name: str):
    """获取单个插件详情（manifest + 全局开关状态）"""
    mgr = _require_manager()
    mf = mgr.get_manifest(name)
    if mf is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    return {**mgr.manifest_to_dict(mf), "global_enabled": await mgr.get_global_enabled(name)}


@router.post("/plugin/{name}/enable", dependencies=[Depends(_auth)])
async def enable_plugin(name: str):
    """全局启用插件（总闸开）"""
    mgr = _require_manager()
    if mgr.get_manifest(name) is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    await mgr.set_global_enabled(name, True)
    return {"name": name, "global_enabled": True}


@router.post("/plugin/{name}/disable", dependencies=[Depends(_auth)])
async def disable_plugin(name: str):
    """全局禁用插件（总闸关）"""
    mgr = _require_manager()
    if mgr.get_manifest(name) is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    await mgr.set_global_enabled(name, False)
    return {"name": name, "global_enabled": False}


@router.get("/plugin/object/{object_id}", dependencies=[Depends(_auth)])
async def get_object_plugins(object_id: str):
    """取某对象所有插件的启用状态 + 生效参数（explicit 标记是否被按对象显式配置）"""
    mgr = _require_manager()
    out = []
    for name in mgr.list_loaded():
        cfg = await mgr.get_object_config(name, object_id)
        out.append({
            "name": name,
            "enabled": await mgr.is_enabled_for(name, object_id),
            "params": await mgr.get_params(name, object_id),
            "explicit": "enabled" in cfg,
        })
    return out


@router.put("/plugin/object/{object_id}/{name}", dependencies=[Depends(_auth)])
async def set_object_plugin(object_id: str, name: str, body: dict):
    """设置某对象某插件：enabled（可选，bool）+ params（可选，dict）。未传项保持不变"""
    mgr = _require_manager()
    if mgr.get_manifest(name) is None:
        raise HTTPException(status_code=404, detail="plugin not found")
    try:
        await mgr.set_object_config(name, object_id, body.get("enabled"), body.get("params"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "object_id": object_id,
        "name": name,
        "enabled": await mgr.is_enabled_for(name, object_id),
        "params": await mgr.get_params(name, object_id),
    }


@router.post("/plugin/{name}/reload", dependencies=[Depends(_auth)])
async def reload_plugin(name: str):
    """热重载插件（重新解析 manifest + 重新加载，热更新配置/代码）"""
    mgr = _require_manager()
    try:
        await mgr.reload(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="plugin not loaded")
    return {"name": name, "reloaded": True}
