"""
MyChat 服务端入口
FastAPI 应用工厂、生命周期、CORS、健康检查、WebSocket 主通道

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.2 创建服务端最小应用骨架：应用工厂、CORS、/health 健康检查
  2. M1.5 挂载 WebSocket 主通道路由（api.ws），接入 tracer bullet 回显
"""
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings  # 同级导入，兼容直接运行与 python -m
from api.ws import router as ws_router  # WebSocket 主通道（M1.5）
from api.rest_persona import router as rest_persona_router  # 人设 REST（M3.1）
from api.rest_memory import router as rest_memory_router  # 记忆 REST（M3.5）


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：初始化默认人设（后续在此加插件管理器、记忆系统等）"""
    # 启动阶段：确保默认人设存在
    from storage.redis_client import get_redis
    from persona.store import init_default_if_absent
    redis = await get_redis()
    await init_default_if_absent(redis)
    yield
    # 关闭阶段：等待在途记忆编码任务完成（带超时，避免卡停机）
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

    return app


app = create_app()
