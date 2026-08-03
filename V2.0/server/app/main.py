"""
MyChat V2.0 服务端入口
FastAPI 应用工厂、生命周期、健康检查、QQ Webhook 路由。

M2 范围:QQ Webhook 收私聊消息 → 连发防抖 → pipeline(persona/记忆/mood/LLM)→ 被动回复。
lifespan 启动:QQ httpx 客户端 + Redis 预热 + 人设/mood 种子 + 插件系统(空载) + mood 衰减循环。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建服务端最小应用骨架:create_app 工厂 + lifespan(httpx 单例)+ /health + 挂 qq_router

2026-06-27
变更说明：
  1. M2 lifespan 整合:人设默认 seed + mood 默认 5 档种表 + 插件系统(空载) + mood 衰减循环

2026-06-28
变更说明：
  1. M3 挂载评分/反推 REST 路由(score_router,/api/v1/chat/.../score、/health、/score/reverse_infer/...)
  2. M4 挂载记忆 REST 路由(memory_router,/api/v1/memory/... 查看/统计/遗忘/恢复/锁定)
  3. M5 lifespan 注册自研工具 + MCP client 连外部 server(无配置降级)
  4. M6 lifespan 加载 .star 兼容层(star_loader,适配到 EventBus/ToolRegistry)

2026-06-30
变更说明：
  1. M7 加 CORSMiddleware + 挂载 Web 面板 REST(chat/mood/plugin/persona/system)+ 暴露 star_loader 单例
  2. M7e 静态托管 dashboard/dist(生产同源省 CORS;dist 不存在则跳过,dev 用 vite :5173 + proxy)

2026-06-30
变更说明：
  1. M8 挂载代答/roleplay REST 路由(takeover_router / roleplay_router,/api/v1/takeover|roleplay/...)

2026-08-04
变更说明：
  1. 修应用 logging 盲区:import 后调 setup_logging(settings.log_level)(core/logging_config dictConfig)
     原未配置致业务 INFO 被 Python 默认 lastResort 丢弃,docker logs 只有 uvicorn access log
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings
from core.logging_config import setup_logging
from qq import api_client as qq_api
from qq import auth as qq_auth
from qq.webhook import router as qq_router
from api.rest_score import router as score_router
from api.rest_memory import router as memory_router
from api.rest_chat import router as chat_router
from api.rest_mood import router as mood_router
from api.rest_plugin import router as plugin_router
from api.rest_persona import router as persona_router
from api.rest_system import router as system_router
from api.rest_takeover import router as takeover_router
from api.rest_roleplay import router as roleplay_router
from api.rest_multimodal import router as multimodal_router

# 配置应用 logging(修盲区:原未配置致业务 INFO 被默认 lastResort 丢弃,仅 WARNING+ 出)
# 必须在 create_app 前调用;dictConfig 整合 uvicorn 走同一 handler/格式(详见 core/logging_config.py)
setup_logging(settings.log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:
    启动:QQ httpx 客户端 → Redis 预热 → 人设/mood 种子 → 插件系统(空载) → mood 衰减循环
    关闭:衰减循环 → 插件 → httpx 客户端"""
    # QQ httpx 客户端(token/发消息复用连接池)
    await qq_auth.init_client()
    await qq_api.init_client()

    # Redis 预热(惰性首连)+ 种子数据初始化
    from storage.redis_client import get_redis
    redis = await get_redis()
    # 灌入面板改过的 QQ 凭证(Redis 覆盖 env;容器重启后从 Redis 恢复,rest_system.PUT 写入)
    from api.rest_system import _apply_credential_overrides
    await _apply_credential_overrides(settings)
    from persona.store import init_default_if_absent
    await init_default_if_absent(redis)         # 默认人设 seed
    from mood.service import seed_default_kinds
    await seed_default_kinds(redis)             # mood 默认 5 档种表(docs/03 §3.2)

    # 插件系统(M2 空载:plugin_dir 无业务插件,仅建 EventBus 供 pipeline 钩子链路;M6 加载 .star)
    from plugins import init_plugins
    await init_plugins(redis)

    # M6 .star 兼容层:加载 .star 插件(适配到 EventBus/ToolRegistry;无 .star 则空载)
    star_loader = None
    if settings.star_enable:
        from plugins import get_event_bus
        from plugins.star_compat.star_loader import StarLoader
        from tools import get_tool_registry
        from core.config import PROJECT_ROOT
        _bus = get_event_bus()
        if _bus is not None:
            star_loader = StarLoader(_bus, get_tool_registry(), redis, settings)
            await star_loader.load_dir(PROJECT_ROOT / settings.star_dir)

    # M7 暴露 StarLoader 单例(供 rest_plugin 调 reload_file;star_enable=False 时登记 None)
    from plugins.star_compat import set_star_loader
    set_star_loader(star_loader)

    # M5 工具系统:注册自研工具(get_persona/write_memory/reverse_infer_trigger/web_search)
    # + MCP client 连外部 server(无配置则降级,只用自研工具)
    from tools import get_tool_registry, register_builtin_tools
    from mcp_client import MCPClient, parse_mcp_servers
    registry = get_tool_registry()
    register_builtin_tools(registry, web_search_enable=settings.web_search_enable)
    mcp_servers = parse_mcp_servers(settings.mcp_servers) if settings.mcp_enable else []
    mcp_client = MCPClient()
    if mcp_servers:
        await mcp_client.connect_all(mcp_servers, registry)

    # mood 衰减循环(独立任务,周期向中性回归)
    from mood.decay import start_decay_loop
    decay_task = start_decay_loop(redis)

    yield

    # 关闭:衰减循环 → MCP client → 插件 → httpx 客户端
    decay_task.cancel()
    try:
        await decay_task
    except asyncio.CancelledError:
        pass
    if mcp_servers:
        await mcp_client.close_all()
    if star_loader is not None:
        await star_loader.unload_all()
    from plugins import shutdown_plugins
    await shutdown_plugins()
    await qq_api.close_client()
    await qq_auth.close_client()


def create_app() -> FastAPI:
    """应用工厂:创建并配置 FastAPI 实例"""
    app = FastAPI(
        title="MyChat V2.0 Server",
        version="2.0.0",
        lifespan=lifespan,
    )

    # M7 Web 面板 CORS:允许 dashboard dev origin(cors_origins 配置,空则默认 localhost:5173)
    from fastapi.middleware.cors import CORSMiddleware
    _raw_origins = (settings.cors_origins or "").strip()
    _origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or [
        "http://localhost:5173", "http://127.0.0.1:5173"]
    app.add_middleware(CORSMiddleware, allow_origins=_origins,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    async def health():
        """健康检查端点(部署存活探测)。附带 QQ 凭证配置状态便于排障(不暴露值)"""
        return {
            "status": "ok",
            "service": "mychat-server-v2",
            "qq_configured": bool(settings.qq_app_id and settings.qq_app_secret),
        }

    # 挂载 QQ Webhook 回调路由(/qq/webhook)
    app.include_router(qq_router)
    # 挂载评分/反推 REST 路由(M3,/api/v1/chat/.../score、/health、/score/reverse_infer/...)
    app.include_router(score_router)
    # 挂载记忆 REST 路由(M4,/api/v1/memory/... 查看/统计/遗忘/恢复/锁定)
    app.include_router(memory_router)
    # M7 挂载 Web 面板 REST 路由(chat 历史/mood 心情/plugin 插件/persona 人设/system 系统)
    app.include_router(chat_router)
    app.include_router(mood_router)
    app.include_router(plugin_router)
    app.include_router(persona_router)
    app.include_router(system_router)
    # M8 挂载代答/roleplay REST 路由(/api/v1/takeover/...、/api/v1/roleplay/...)
    app.include_router(takeover_router)
    app.include_router(roleplay_router)
    # M-vision 挂载图像理解 REST 路由(POST /api/v1/multimodal/vision 上传图→GLM 描述)
    app.include_router(multimodal_router)
    # M7e 静态托管前端构建产物 + SPA history mode 兜底(修子路由刷新 404);dist 不存在则跳过(dev 走 vite proxy)
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    from core.config import PROJECT_ROOT
    _dist = PROJECT_ROOT / "dashboard" / "dist"
    if _dist.is_dir():
        _dist_resolved = _dist.resolve()

        @app.get("/{full_path:path}")
        async def spa_serve(full_path: str):
            """SPA 静态托管 + history mode 兜底(替代 StaticFiles mount)。
            API/health/qq 路由由上方 include_router 先声明优先匹配,不被吞。
            dist 下真实文件(/assets/*.js 等)→ FileResponse 该文件;否则 → index.html(Vue Router 接管刷新/深链)。
            path traversal 防护:解析后必须仍在 _dist 下。"""
            target = (_dist / full_path).resolve()
            try:
                target.relative_to(_dist_resolved)
            except ValueError:
                raise HTTPException(status_code=404)
            if full_path and target.is_file():
                return FileResponse(str(target))
            return FileResponse(str(_dist / "index.html"))
    return app


app = create_app()
