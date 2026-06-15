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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings  # 同级导入，兼容直接运行与 python -m
from api.ws import router as ws_router  # WebSocket 主通道（M1.5）


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：后续在此初始化 Redis 连接、插件管理器、记忆系统等"""
    # 启动阶段
    yield
    # 关闭阶段


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

    return app


app = create_app()
