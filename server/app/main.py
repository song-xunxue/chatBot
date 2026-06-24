"""
MyChat 服务端入口
FastAPI 应用工厂、生命周期、CORS、健康检查、WebSocket 主通道

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.2 创建服务端最小应用骨架：应用工厂、CORS、/health 健康检查
  2. M1.5 挂载 WebSocket 主通道路由（api.ws），接入 tracer bullet 回显

2026-06-24
变更说明：
  1. M4.1/M4.2 lifespan 接入插件系统(init_plugins/shutdown_plugins，失败降级)；挂载插件 REST
"""
import logging
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings  # 同级导入，兼容直接运行与 python -m
from api.ws import router as ws_router  # WebSocket 主通道（M1.5）
from api.rest_persona import router as rest_persona_router  # 人设 REST（M3.1）
from api.rest_memory import router as rest_memory_router  # 记忆 REST（M3.5）
from api.rest_plugin import router as rest_plugin_router  # 插件 REST（M4.2）
from api.rest_pet import router as rest_pet_router  # 桌宠头像 REST（M6.1）
from api.rest_multimodal import router as rest_multimodal_router  # 多模态理解 REST（M6.2）
from api.rest_admin import router as rest_admin_router  # 管理面板杂项 REST（M7）
from api.rest_roleplay import router as rest_roleplay_router  # 代人聊天 A 模拟训练 REST（V1.1 M11）

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：初始化默认人设、插件系统（M4）"""
    # 启动阶段：确保默认人设存在
    from storage.redis_client import get_redis
    from persona.store import init_default_if_absent
    redis = await get_redis()
    await init_default_if_absent(redis)
    # M4：初始化插件系统（失败降级为无插件，不影响主流程）
    try:
        from plugins import init_plugins
        await init_plugins(redis)
    except Exception:
        logger.exception("plugin system init failed, continuing without plugins")
    # M4.4：启动 on_tick 调度器（驱动 mood/time/proactive 等定时插件）
    try:
        from plugins import get_event_bus
        from plugins.connections import get_connection_registry
        from plugins.scheduler import TickScheduler
        _bus = get_event_bus()
        if _bus is not None:
            app.state.tick_scheduler = TickScheduler(_bus, get_connection_registry(),
                                                     interval=settings.plugin_tick_interval)
            app.state.tick_scheduler.start()
    except Exception:
        logger.exception("tick scheduler start failed")
    yield
    # 关闭阶段：先停调度器 → 卸载插件 → drain 记忆后台任务
    _sched = getattr(app.state, "tick_scheduler", None)
    if _sched is not None:
        try:
            await _sched.stop()
        except Exception:
            logger.exception("tick scheduler stop failed")
    try:
        from plugins import shutdown_plugins
        await shutdown_plugins()
    except Exception:
        logger.exception("plugin shutdown failed")
    # 等待在途记忆编码任务完成（带超时，避免卡停机）
    from pipeline.stages import _BG_TASKS
    pending = [t for t in _BG_TASKS if not t.done()]
    if pending:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True), timeout=10.0)


def create_app() -> FastAPI:
    """应用工厂：创建并配置 FastAPI 实例"""
    app = FastAPI(
        title="MyChat Server",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS：允许客户端与面板跨域访问（单人场景先放开，后续可收紧）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        """健康检查端点，用于部署后的存活探测（对应 NFR-A-01 可用性）"""
        return {"status": "ok", "service": "mychat-server"}

    # 挂载 WebSocket 主通道（M1.5 tracer bullet：回显；后续接入完整管道）
    app.include_router(ws_router)
    # 挂载人设 REST 接口（M3.1）
    app.include_router(rest_persona_router)
    # 挂载记忆 REST 接口（M3.5）
    app.include_router(rest_memory_router)
    # 挂载插件 REST 接口（M4.2）
    app.include_router(rest_plugin_router)
    # 挂载桌宠头像 REST 接口（M6.1）
    app.include_router(rest_pet_router)
    # 挂载多模态理解 REST 接口（M6.2）
    app.include_router(rest_multimodal_router)
    # 挂载管理面板杂项 REST 接口（M7）
    app.include_router(rest_admin_router)
    app.include_router(rest_roleplay_router)
    # M8：托管 Vue 管理面板静态产物（在所有 API 路由之后挂载，浏览器直开 /）
    _mount_dashboard(app)

    return app


def _mount_dashboard(app: FastAPI) -> None:
    """挂载 Vue 面板 dist 到 /（容器内 /app/dashboard_dist；本地 dashboard/dist）。
    在所有 API 路由之后挂载，/api /ws /health 优先匹配；dist 不存在则跳过。"""
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    for d in (Path("/app/dashboard_dist"), Path(__file__).resolve().parents[2] / "dashboard" / "dist"):
        if d.is_dir():
            app.mount("/", StaticFiles(directory=str(d), html=True), name="dashboard")
            logger.info("dashboard mounted at / from %s", d)
            return


app = create_app()
