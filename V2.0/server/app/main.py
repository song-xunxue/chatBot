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
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings
from qq import api_client as qq_api
from qq import auth as qq_auth
from qq.webhook import router as qq_router
from api.rest_score import router as score_router
from api.rest_memory import router as memory_router

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
    from persona.store import init_default_if_absent
    await init_default_if_absent(redis)         # 默认人设 seed
    from mood.service import seed_default_kinds
    await seed_default_kinds(redis)             # mood 默认 5 档种表(docs/03 §3.2)

    # 插件系统(M2 空载:plugin_dir 无业务插件,仅建 EventBus 供 pipeline 钩子链路;M6 加载 .star)
    from plugins import init_plugins
    await init_plugins(redis)

    # mood 衰减循环(独立任务,周期向中性回归)
    from mood.decay import start_decay_loop
    decay_task = start_decay_loop(redis)

    yield

    # 关闭:衰减循环 → 插件 → httpx 客户端
    decay_task.cancel()
    try:
        await decay_task
    except asyncio.CancelledError:
        pass
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

    # QQ 回调是服务端到服务端(无浏览器 origin),M2 不加 CORSMiddleware;M7 加 Web 面板时再加

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
    return app


app = create_app()
