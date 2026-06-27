"""
Redis 异步客户端(单例)
从 settings.redis_url 建立连接;若配置了 REDIS_PASSWORD 则注入到 URL。
decode_responses=True 使返回值为 str(免去手动 decode)。

V2.0 用途:QQ access_token 缓存(M1)/后续 chat_store 三层结构/心情/记忆(M2+)。
键前缀沿用 mychat:(与 docs/02/03 文档约定一致,token 键 mychat:qq:access_token)。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建 Redis 异步单例(从 V1.0 copy 同款实现,自动适配可选密码)
"""
from redis.asyncio import Redis  # redis-py 内置异步客户端

from core.config import settings

_redis: Redis | None = None  # 全局连接单例


async def get_redis() -> Redis:
    """获取 Redis 异步连接单例(首次调用时建立)"""
    global _redis
    if _redis is None:
        url = settings.redis_url
        # 若配置了密码,注入到 URL:redis://host -> redis://:pwd@host
        if settings.redis_password:
            url = url.replace("redis://", f"redis://:{settings.redis_password}@")
        _redis = Redis.from_url(url, decode_responses=True)
    return _redis
