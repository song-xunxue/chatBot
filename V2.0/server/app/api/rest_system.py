"""
系统配置 REST 接口(M7):provider 配置状态(只读)+ 重载配置(in-place 刷新 settings)。
对应 V2.0 .env 模型架构(不做运行时切换,改 .env 后点重载即时生效,不重启进程)。鉴权 X-Access-Token。

路由(prefix /api/v1):
  GET  /system/config    provider 配置状态(available_providers,不暴露 api_key)
  POST /system/reload    重载配置(重读 .env + in-place 覆盖 settings 单例 + 重建 QQ httpx 客户端)

作者: 李文煜
日期: 2026-06-30
"""
import logging

from fastapi import APIRouter, Depends

from api._auth import verify_token
from llm.registry import available_providers, provider_specs
from core.config import settings, Settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/system/config", dependencies=[Depends(verify_token)])
async def system_config():
    """provider 配置状态(展示名 + available/configured,不暴露 api_key)。
    从 llm.registry.provider_specs() 生成(单一注册表,#7 不再维护第三份 provider 名单)。"""
    avail = set(available_providers())
    return {
        "providers": [
            {"name": s.name, "display": s.display,
             "available": s.name in avail,
             "configured": bool(getattr(settings, s.key_attr, ""))}
            for s in provider_specs()
        ],
        "available": sorted(avail),
    }


@router.post("/system/reload", dependencies=[Depends(verify_token)])
async def reload_config():
    """重载配置:重读 .env(Settings())→ 逐字段 in-place 覆盖 settings 单例 → 重建 QQ httpx 客户端。
    provider 无需重建(get_provider 每次新建读 settings,自动用新 key)。不重启进程、不断连、
    不打断在途请求(在途请求用旧实例跑完,新请求用新配置)。"""
    fresh = Settings()
    for f in type(fresh).model_fields:    # type(fresh) 即 Settings 真类(避免 Settings 名被替换时取不到类属性)
        setattr(settings, f, getattr(fresh, f))
    # 重建有状态的 QQ httpx 客户端(token 缓存清);失败不影响 settings 已刷新
    from qq import auth as qq_auth, api_client as qq_api
    try:
        await qq_auth.close_client()
        await qq_api.close_client()
        await qq_auth.init_client()
        await qq_api.init_client()
    except Exception:
        logger.exception("reload: QQ client rebuild failed (settings still refreshed)")
    return {"reloaded": True, "providers": sorted(available_providers())}
