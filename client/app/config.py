"""
客户端配置：从环境变量读服务端地址、令牌、聊天对象、SQLite 路径、消息上限。
部署后用 CLIENT_SERVER_URL 指向服务器；本地开发默认 127.0.0.1:8000。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建客户端配置加载（ws/rest/token/object/db/limit）
"""
import os
from dataclasses import dataclass
from pathlib import Path

# 项目根：client/app/config.py → parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ClientConfig:
    ws_url: str            # WebSocket 主通道
    rest_url: str          # REST 管理/配置通道
    token: str             # 访问令牌（与服务端 access_token 一致）
    object_id: str         # 聊天对象 ID（单人场景固定）
    db_path: Path          # 本地 SQLite 缓存路径
    message_limit: int     # 单对象消息保存上限（超出清理最旧，Q-04）
    user_avatar: str = ""  # 用户头像本地路径（空则用默认 svg；可由顶栏"我"按钮改图）


def load_config() -> ClientConfig:
    """从环境变量加载客户端配置（默认本地开发值）"""
    base = os.environ.get("CLIENT_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
    ws = os.environ.get("CLIENT_WS_URL", base.replace("http://", "ws://", 1).replace("https://", "wss://", 1) + "/ws")
    db_path = Path(os.environ.get("CLIENT_DB_PATH", str(PROJECT_ROOT / "client" / "data" / "chat.db")))
    return ClientConfig(
        ws_url=ws,
        rest_url=os.environ.get("CLIENT_REST_URL", base),
        token=os.environ.get("ACCESS_TOKEN", "change-me-please"),
        object_id=os.environ.get("CLIENT_OBJECT_ID", "default"),
        db_path=db_path,
        message_limit=int(os.environ.get("CLIENT_MESSAGE_LIMIT", "500")),
        user_avatar=os.environ.get("CLIENT_USER_AVATAR", str(PROJECT_ROOT / "client" / "data" / "user_avatar.png")),
    )
