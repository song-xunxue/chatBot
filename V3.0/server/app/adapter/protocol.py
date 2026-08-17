"""
平台出站契约(V3.0 M-V3-1):平台无关的消息发送接口。
official / onebot 各一实现;pipeline 零依赖(只产 ctx.reply_text,由调用方经本契约下发)。

设计约定(与 V2.0 qq/api_client 行为对齐,调用方 try/except 降级逻辑不变):
- 失败抛异常(official=httpx 原异常;onebot=RuntimeError),成功返 dict。
- send_text 出站守卫(human_authored=False 过 sanitize_reply)是两实现共同的不变量(架构 #3)。
- msg_id/msg_seq:official 被动回复语义(60min 窗口/防同 msg_id 重复);onebot 忽略(主动直发,无配额)。

作者: 李文煜
日期: 2026-08-16
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class PlatformAdapter(Protocol):
    """平台出站契约。oid 语义:official=QQ openid(32位);onebot=QQ 号(user_id 字符串)。"""

    async def send_text(self, oid: str, content: str, *, msg_id: str = "",
                        msg_seq: int = 1, human_authored: bool = False) -> dict:
        """发文本。human_authored=True 跳过出站守卫(admin 代答原文)。
        返回 dict(official=QQ 响应 {id,timestamp};onebot={delivered,mode})。"""
        ...

    async def send_voice(self, oid: str, silk_bytes: bytes, *, msg_id: str = "",
                         msg_seq: int = 1, content: str = "") -> dict:
        """发语音(silk bytes;QQ 语音统一格式)。失败抛异常,调用方降级文本。"""
        ...

    async def init(self) -> None:
        """启动(httpx 客户端/WS 通道等)"""
        ...

    async def close(self) -> None:
        """关闭(释放资源)"""
        ...
