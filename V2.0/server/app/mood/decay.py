"""
心情衰减任务
mood 向中性值(neutral)周期衰减(久无互动趋于平静),对应 docs/03 §4.1 on_tick 规则。
V2.0 mood 融入架构后不再是插件,故不走 ON_TICK 钩子,改用独立 asyncio 衰减循环。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 新建 mood decay:decay_step/decay_all + start_decay_loop(独立循环,main.py lifespan 启动)
"""
import asyncio
import logging

from redis.asyncio import Redis

from mood import service
from core.config import settings

logger = logging.getLogger(__name__)


async def decay_step(redis: Redis, object_id: str, *,
                     decay: float | None = None, neutral: float | None = None) -> float:
    """单对象 mood 衰减一步:mood > neutral 向下 decay / < neutral 向上 decay。
    默认参数读 settings.mood_decay / settings.mood_neutral。返回衰减后 mood。"""
    decay = settings.mood_decay if decay is None else decay
    neutral = settings.mood_neutral if neutral is None else neutral
    mood = await service.get_mood(redis, object_id)
    if mood > neutral:
        mood = max(neutral, mood - decay)
    elif mood < neutral:
        mood = min(neutral, mood + decay)
    await service.set_mood(redis, object_id, mood)
    return mood


async def decay_all(redis: Redis) -> int:
    """对所有有 mood 记录的对象执行一次衰减,返回处理对象数"""
    oids = await service.list_mood_objects(redis)
    for oid in oids:
        await decay_step(redis, oid)
    return len(oids)


async def _decay_loop(redis: Redis, interval: float) -> None:
    """衰减主循环:每 interval 秒对所有对象衰减一轮"""
    while True:
        await asyncio.sleep(interval)
        try:
            await decay_all(redis)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("mood decay loop iteration failed")


def start_decay_loop(redis: Redis, interval: float | None = None) -> asyncio.Task:
    """启动衰减循环(返回 Task,供 lifespan 关闭时 cancel)。间隔默认 settings.plugin_tick_interval"""
    interval = settings.plugin_tick_interval if interval is None else interval
    return asyncio.create_task(_decay_loop(redis, interval))
