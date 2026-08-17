"""astrbot.api.event 兼容(V2.0 子集):AstrMessageEvent(适配 V2.0 MessageContext)+ filter 装饰器。

作者: 李文煜
日期: 2026-06-28
"""


class MessageEventResult:
    """handler 返回值(简化:仅 text)"""
    def __init__(self, text: str = "", **kw):
        self.text = text


class AstrMessageEvent:
    """V2.0 MessageContext 适配(子集):.star 插件 handler 接收的事件对象。
    暴露 AstrBot 私聊场景能提供的字段;深度 API(群/@/平台)不提供。"""

    def __init__(self, mctx):
        self._mctx = mctx                        # V2.0 pipeline.context.MessageContext
        self.message_str = mctx.user_text        # 用户文本(AstrBot message_str)
        self.plain_text = mctx.user_text
        self._stopped = False

    @property
    def unified_msg_origin(self) -> str:         # AstrBot 会话标识(=V2.0 object_id)
        return self._mctx.object_id

    @property
    def message_obj(self):                        # AstrBot message_obj(简化返自身)
        return self

    @property
    def nickname(self) -> str:
        return self._mctx.object_id

    def get_message_type(self) -> str:            # V2.0 仅私聊
        return "private"

    def is_stopped(self) -> bool:
        return self._stopped

    def stop_event(self) -> None:                 # 停止事件传播(对应 AstrBot)
        self._stopped = True

    def plain_result(self, text: str) -> MessageEventResult:
        return MessageEventResult(text=text)

    async def send(self, text: str) -> None:
        """发送额外消息(简化:累积到 plugin_meta,由 V2.0 适配层处理)"""
        self._mctx.plugin_meta.setdefault("_star_send", []).append(text)


from astrbot.api.event.filter import (   # noqa: E402(兼容 AstrBot from astrbot.api.event import filter)
    command, regex, on_llm_request, on_llm_response, after_message_sent, llm_tool,
)
