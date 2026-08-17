"""
平台适配器层(V3.0,2026-08-17 精简为纯 OneBot)
V3.0 定位 = QQ 号(真人身份)项目:唯一出站实现 OnebotAdapter(经 NapCat 反向 WS)。
历史:2026-08-16 M-V3-1 曾双栈(official|onebot 配置驱动),08-17 按用户方向裁撤 official——
V2.0 才是官方机器人项目(独立演进);通用优化(记忆/拟人化等)两项目双向复用。

作者: 李文煜
日期: 2026-08-16

2026-08-17
变更说明：
  1. 精简:删 official 实现/工厂分支/ADAPTER 配置,恒返回 OnebotAdapter
"""
import logging

from adapter.onebot import OnebotAdapter

logger = logging.getLogger(__name__)

_current = None


async def get_current_adapter() -> OnebotAdapter:
    """取 OnebotAdapter 单例(懒初始化)。WS 出站通道由 onebot/ws_client 维护(NapCat 连入)。"""
    global _current
    if _current is None:
        _current = OnebotAdapter()
        await _current.init()
        logger.info("平台适配器已初始化: onebot")
    return _current


def reset_adapter() -> None:
    """重置单例(测试用)"""
    global _current
    _current = None
