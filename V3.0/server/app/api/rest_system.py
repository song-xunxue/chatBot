"""
系统配置 REST 接口(M7):provider 配置状态(只读)+ 重载配置(in-place 刷新 settings)。
对应 .env 模型架构(不做运行时切换,改 .env 后点重载即时生效,不重启进程)。鉴权 X-Access-Token。

路由(prefix /api/v1):
  GET  /system/config          provider 配置状态(available_providers,不暴露 api_key)
  POST /system/reload          重载配置(重读 .env + in-place 覆盖 settings 单例)
  POST /system/reset           清空所有运行时数据,保留人设+配置(2026-07-05,需 confirm='清空')

作者: 李文煜
日期: 2026-06-30

2026-07-05
变更说明：
  1. 面板改造:新增 POST /system/reset(全局清空运行时数据,白名单保留人设+配置),需 confirm='清空' 防误触

2026-07-06
变更说明：
  1. B-1 修 reset 白名单:KEEP_PREFIXES 加 mychat:mood:kind:(原漏此前缀,reset 误删档位 Hash 但留索引致 mood 瘫痪)

2026-08-17
变更说明：
  1. V3.0 精简:删 qq-credentials 端点与 _apply_credential_overrides(V3.0 纯 OneBot 无官方凭证)
"""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException

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
    """重载配置:重读 .env(Settings())→ 逐字段 in-place 覆盖 settings 单例。
    provider 无需重建(get_provider 每次新建读 settings,自动用新 key)。不重启进程、不断连、
    不打断在途请求(在途请求用旧实例跑完,新请求用新配置)。"""
    fresh = Settings()
    for f in type(fresh).model_fields:    # type(fresh) 即 Settings 真类(避免 Settings 名被替换时取不到类属性)
        setattr(settings, f, getattr(fresh, f))
    return {"reloaded": True, "providers": sorted(available_providers())}


@router.post("/system/reset", dependencies=[Depends(verify_token)])
async def reset_all_data(body: dict = Body(default={})):
    """清空所有运行时数据,只保留人设 + 系统配置(2026-07-05 面板改造)。
    保留白名单:mychat:persona:*/persona_version:*/obj:*(人设+绑定)/config:*(QQ凭证等)/qq:*(token缓存)/
              mood:kinds|mood:params(心情配置)/plugin:*(全局开关)。
    清空:聊天记录/roleplay训练样本/四级记忆/评分样本/mood值+历史/代答队列/per-object插件配置/插件运行时缓冲。
    body 须 {confirm:"清空"} 防误触。返回 {deleted, kept} 键计数。"""
    if body.get("confirm") != "清空":
        raise HTTPException(status_code=400, detail="请传入 confirm='清空' 确认")
    from storage.redis_client import get_redis
    redis = await get_redis()
    KEEP_EXACT = {"mychat:mood:kinds", "mychat:mood:params"}
    # mychat:mood:kind: 前缀保留档位 Hash(2026-07-06 B-1 修:原白名单漏此前缀,reset 误删档位 Hash
    # 但留索引 ZSET mood:kinds,致 mood 系统瘫痪、面板档位栏位全空)。此前缀不误匹配 mood:kinds
    # (第 17 字符 ':' != 's',字符串前缀比较安全)
    KEEP_PREFIXES = ("mychat:persona:", "mychat:persona_version:", "mychat:obj:",
                     "mychat:config:", "mychat:qq:", "mychat:plugin:", "mychat:mood:kind:")
    deleted = 0
    kept = 0
    async for key in redis.scan_iter(match="mychat:*", count=200):
        k = key.decode() if isinstance(key, bytes) else key
        if k in KEEP_EXACT or any(k.startswith(p) for p in KEEP_PREFIXES):
            kept += 1
            continue
        await redis.delete(k)
        deleted += 1
    logger.warning("系统重置:删除 %d 键,保留 %d 键(人设+配置白名单)", deleted, kept)
    return {"deleted": deleted, "kept": kept}
