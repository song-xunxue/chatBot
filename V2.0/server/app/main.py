"""
MyChat V2.0 服务端入口
FastAPI 应用工厂、生命周期、健康检查、QQ Webhook 路由。

M1 范围:QQ 官方机器人 Webhook 收私聊消息 → echo 回发(被动回复),验证整条链路。
不挂 V1.0 的 ws_router(V2.0 砍 WS 客户端通道);pipeline/人设/记忆留 M2+。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建服务端最小应用骨架:create_app 工厂 + lifespan(httpx 单例)+ /health + 挂 qq_router
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings  # 同级导入,兼容直接运行与 python -m
from qq import api_client as qq_api
from qq import auth as qq_auth
from qq.webhook import router as qq_router  # QQ Webhook 回调路由

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:创建 httpx 客户端单例(token/发消息复用连接池);关闭时释放"""
    await qq_auth.init_client()
    await qq_api.init_client()
    yield
    await qq_api.close_client()
    await qq_auth.close_client()


def create_app() -> FastAPI:
    """应用工厂:创建并配置 FastAPI 实例"""
    app = FastAPI(
        title="MyChat V2.0 Server",
        version="2.0.0",
        lifespan=lifespan,
    )

    # QQ 回调是服务端到服务端(无浏览器 origin),M1 不加 CORSMiddleware;M7 加 Web 面板时再加

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
    return app


app = create_app()
