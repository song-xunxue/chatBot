"""
服务端配置加载
基于 pydantic-settings 从项目根 .env 读取配置。

V2.0 重点是 QQ 官方机器人(Webhook)接入,凭证只需 2 个:
  - QQ AppID:机器人 ID
  - QQ AppSecret:既换 access_token(调 QQ REST 发消息),又作 Webhook 回调 Ed25519 验签密钥派生源
    (QQ 文档术语「Bot Secret」即此字段;OpenClaw/AstrBot/阿里云接入均只需 2 凭证佐证,用户后台确认无独立 Bot Secret)

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建配置模块:服务端/Redis/QQ 凭证(AppID+AppSecret)统一从项目根 .env 加载
  2. 凭证从「AppSecret+BotSecret 双凭证」修正为「单 AppSecret」(用户后台确认无独立 Bot Secret)
"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录(本文件位于 server/app/core/,向上三级到项目根 V2.0/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """服务端配置:字段名小写,自动映射 .env 中的大写键;extra=ignore 忽略未声明键(如 M2+ 才用的 LLM key)"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),  # 从项目根 .env 读取
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 .env 中未声明的键(如 GLM_API_KEY 等 M2+ 才用的字段)
    )

    # 1.服务端
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    access_token: str = "change-me-please"  # 单人场景访问令牌(Web 面板 REST 鉴权,M7 用)

    # 2.Redis(云端 Docker)
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""

    # 3.QQ 官方机器人凭证(只需 AppID + AppSecret;AppSecret 既换 token 又作 Ed25519 验签密钥派生源)
    qq_app_id: str = Field(default="", validation_alias="APPID")  # .env 旧字段 APPID(无下划线),显式别名映射
    qq_app_secret: str = Field(default="", validation_alias="QQ_APP_SECRET")  # 既换 access_token,又作 Ed25519 验签密钥派生源
    # QQ API 端点 base(便于切沙箱 sandbox.api.sgroup.qq.com,默认正式环境)
    qq_api_base: str = "https://api.sgroup.qq.com"  # 发消息 REST base
    qq_token_base: str = "https://bots.qq.com/app"  # 换 access_token 接口 base
    qq_webhook_public_url: str = ""  # Webhook 回调公网 URL(部署/调试用,代码可不读)
    qq_signature_max_skew_sec: int = 300  # 验签时间戳防重放容忍秒数(QQ 推荐 300)

    # 4.LLM Providers(M2+ 才用,M1 暂不声明,extra=ignore 自动兼容 .env 里已有的 key)


# 全局配置单例
settings = Settings()
