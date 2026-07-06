"""
系统配置 REST 接口(M7):provider 配置状态(只读)+ 重载配置(in-place 刷新 settings)。
对应 V2.0 .env 模型架构(不做运行时切换,改 .env 后点重载即时生效,不重启进程)。鉴权 X-Access-Token。

路由(prefix /api/v1):
  GET  /system/config          provider 配置状态(available_providers,不暴露 api_key)
  POST /system/reload          重载配置(重读 .env + in-place 覆盖 settings 单例 + 重建 QQ httpx 客户端)
  GET  /system/qq-credentials  QQ 凭证状态(app_id 明文,secret 仅 has_secret)
  PUT  /system/qq-credentials  更新 QQ 凭证(写 Redis + 热生效)
  POST /system/reset           清空所有运行时数据,保留人设+配置(2026-07-05,需 confirm='清空')

作者: 李文煜
日期: 2026-06-30

2026-07-05
变更说明：
  1. 面板改造:新增 POST /system/reset(全局清空运行时数据,白名单保留人设+配置),需 confirm='清空' 防误触

2026-07-06
变更说明：
  1. B-1 修 reset 白名单:KEEP_PREFIXES 加 mychat:mood:kind:(原漏此前缀,reset 误删档位 Hash 但留索引致 mood 瘫痪)
"""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from api._auth import verify_token
from llm.registry import available_providers, provider_specs
from core.config import settings, Settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["system"])

# QQ 凭证面板化管理(持久化 Redis;启动/reload 灌入 settings 覆盖 env)
_K_QQ_APP_ID = "mychat:config:qq_app_id"
_K_QQ_APP_SECRET = "mychat:config:qq_app_secret"


async def _apply_credential_overrides(settings_obj) -> None:
    """从 Redis 灌入面板改过的 QQ 凭证(覆盖 env 值)。Redis 无值则不动(保留 env)。
    启动(lifespan)+ reload 后调 —— docker-compose env_file 注入 env vars 优先于 .env 文件,
    且容器内无 .env 文件,故面板持久化走 Redis(有 volume),不写 .env。"""
    from storage.redis_client import get_redis
    try:
        redis = await get_redis()
        app_id = await redis.get(_K_QQ_APP_ID)
        secret = await redis.get(_K_QQ_APP_SECRET)
        if app_id:
            settings_obj.qq_app_id = app_id
        if secret:
            settings_obj.qq_app_secret = secret
    except Exception:
        logger.exception("apply_credential_overrides 失败(redis 不可用?),保留 env 值")


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


@router.get("/system/qq-credentials", dependencies=[Depends(verify_token)])
async def get_qq_credentials():
    """QQ 机器人凭证状态:app_id 明文(非敏感,机器人标识);secret 仅返 has_secret(不泄露,
    泄露可被冒充调 QQ API)。"""
    return {"app_id": settings.qq_app_id, "has_secret": bool(settings.qq_app_secret)}


@router.put("/system/qq-credentials", dependencies=[Depends(verify_token)])
async def set_qq_credentials(body: dict = Body(default={})):
    """更新 QQ 凭证:写 Redis 持久化 + setattr settings + 删旧 access_token 缓存 + 重建 httpx 客户端。
    热生效(凭证消费点 auth/webhook 每次现读 settings,无需重启容器)。app_id/app_secret 均必填。"""
    app_id = str(body.get("app_id", "")).strip()
    secret = str(body.get("app_secret", "")).strip()
    if not app_id or not secret:
        raise HTTPException(status_code=400, detail="app_id 和 app_secret 必填")
    from storage.redis_client import get_redis
    from qq.auth import _TOKEN_KEY
    redis = await get_redis()
    await redis.set(_K_QQ_APP_ID, app_id)
    await redis.set(_K_QQ_APP_SECRET, secret)
    settings.qq_app_id = app_id
    settings.qq_app_secret = secret
    await redis.delete(_TOKEN_KEY)   # 清旧 token(旧 secret 换的),强制下次用新 secret 换
    from qq import auth as qq_auth, api_client as qq_api
    try:
        await qq_auth.close_client(); await qq_api.close_client()
        await qq_auth.init_client(); await qq_api.init_client()
    except Exception:
        logger.exception("QQ 凭证更新后重建客户端失败(settings 已更新)")
    return {"ok": True, "qq_configured": True}


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
    # 应用面板改过的 QQ 凭证覆盖(reload 从 env 重读后,再 merge Redis,避免面板值被 reload 冲掉)
    await _apply_credential_overrides(settings)
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
