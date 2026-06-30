"""
插件管理 REST 接口(M7):原生插件 + .star 插件统一视图 + 启用/禁用/热重载。
原生走 PluginManager,.star 走 StarLoader.reload_file(增量)。鉴权 X-Access-Token。

路由(prefix /api/v1):
  GET   /plugin                          列全部插件(原生 + .star 合并)
  GET   /plugin/{name}                   取单插件(原生优先,其次 .star)
  POST  /plugin/{name}/enable            启用(原生全局开关)
  POST  /plugin/{name}/disable           禁用(原生全局开关)
  POST  /plugin/{name}/reload            热重载(原生 reload;若为 .star 走 star reload_file)
  POST  /plugin/star/{name}/reload       .star 增量热重载(reload_file)
  GET   /plugin/object/{oid}             列某对象的插件启用状态(原生)
  PUT   /plugin/object/{oid}/{name}      设置某对象插件配置(原生)

作者: 李文煜
日期: 2026-06-30
"""
from fastapi import APIRouter, Body, Depends, HTTPException

from api._auth import verify_token
from plugins import get_plugin_manager
from plugins.star_compat import get_star_loader

router = APIRouter(prefix="/api/v1", tags=["plugin"])


def _native_dict(mgr, name) -> dict:
    """原生插件序列化(manifest + enabled)"""
    mf = mgr.get_manifest(name)
    d = mgr.manifest_to_dict(mf) if mf else {"name": name}
    d["type"] = "native"
    return d


def _star_dict(name: str) -> dict:
    """.star 插件摘要"""
    return {"name": name, "type": "star", "enabled": True}


@router.get("/plugin", dependencies=[Depends(verify_token)])
async def list_plugins():
    """列全部插件:原生(PluginManager.list_loaded)+ .star(StarLoader.list_loaded)合并"""
    out = []
    mgr = get_plugin_manager()
    if mgr is not None:
        for name in mgr.list_loaded():
            d = _native_dict(mgr, name)
            d["enabled"] = await mgr.get_global_enabled(name)
            out.append(d)
    star = get_star_loader()
    if star is not None:
        for name in star.list_loaded():
            out.append(_star_dict(name))
    return out


@router.get("/plugin/{name}", dependencies=[Depends(verify_token)])
async def get_plugin(name: str):
    """取单插件(原生优先,其次 .star)"""
    mgr = get_plugin_manager()
    if mgr is not None and name in mgr.list_loaded():
        d = _native_dict(mgr, name)
        d["enabled"] = await mgr.get_global_enabled(name)
        return d
    star = get_star_loader()
    if star is not None and name in star.list_loaded():
        return _star_dict(name)
    raise HTTPException(status_code=404, detail="plugin not found")


@router.post("/plugin/{name}/enable", dependencies=[Depends(verify_token)])
async def enable_plugin(name: str):
    mgr = get_plugin_manager()
    if mgr is None or name not in mgr.list_loaded():
        raise HTTPException(status_code=404, detail="native plugin not found")
    await mgr.set_global_enabled(name, True)
    return {"name": name, "enabled": True}


@router.post("/plugin/{name}/disable", dependencies=[Depends(verify_token)])
async def disable_plugin(name: str):
    mgr = get_plugin_manager()
    if mgr is None or name not in mgr.list_loaded():
        raise HTTPException(status_code=404, detail="native plugin not found")
    await mgr.set_global_enabled(name, False)
    return {"name": name, "enabled": False}


@router.post("/plugin/{name}/reload", dependencies=[Depends(verify_token)])
async def reload_plugin(name: str):
    """热重载:原生走 manager.reload;.star 走 star reload_file"""
    mgr = get_plugin_manager()
    if mgr is not None and name in mgr.list_loaded():
        try:
            await mgr.reload(name)
            return {"name": name, "type": "native", "reloaded": True}
        except KeyError:
            raise HTTPException(status_code=404, detail="plugin not loaded")
    star = get_star_loader()
    if star is not None and await star.reload_file(name):
        return {"name": name, "type": "star", "reloaded": True}
    raise HTTPException(status_code=404, detail="plugin not found or reload failed")


@router.post("/plugin/star/{name}/reload", dependencies=[Depends(verify_token)])
async def reload_star(name: str):
    """.star 增量热重载(避开 clear_registry 全清)"""
    star = get_star_loader()
    if star is None:
        raise HTTPException(status_code=503, detail="star loader not initialized")
    if not await star.reload_file(name):
        raise HTTPException(status_code=404, detail="star plugin not found or reload failed")
    return {"name": name, "type": "star", "reloaded": True}


@router.get("/plugin/object/{oid}", dependencies=[Depends(verify_token)])
async def object_plugins(oid: str):
    """列某对象的插件启用状态(原生 is_enabled_for)"""
    mgr = get_plugin_manager()
    if mgr is None:
        return []
    out = []
    for name in mgr.list_loaded():
        out.append({"name": name, "type": "native", "enabled": await mgr.is_enabled_for(name, oid)})
    return out


@router.put("/plugin/object/{oid}/{name}", dependencies=[Depends(verify_token)])
async def set_object_plugin(oid: str, name: str, body: dict = Body(default={})):
    """设置某对象插件配置(原生)。body: {enabled?, params?}"""
    mgr = get_plugin_manager()
    if mgr is None or name not in mgr.list_loaded():
        raise HTTPException(status_code=404, detail="native plugin not found")
    try:
        await mgr.set_object_config(name, oid,
                                    enabled=body.get("enabled"),
                                    params=body.get("params"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"name": name, "object_id": oid, "params": await mgr.get_params(name, oid)}
