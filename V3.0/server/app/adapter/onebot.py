"""
onebot 适配器(V3.0 M-V3-1):经 NapCat 反向 WS 发 OneBot v11 Action。
出站通道由 onebot/ws_client 维护(NapCat 主动连入的 WS 连接);本适配器只发 Action + 等响应。

- 文本:send_private_msg;出站守卫与 official 同构(human_authored=False 过 sanitize_reply,架构 #3)。
- 语音:CQ record 码 + base64(silk;QQ 语音统一格式,NapCat 直接下发音 Voice 条)。
- msg_id/msg_seq 忽略(OneBot 个人号无被动回复窗口/月配额概念,主动直发)。
- 失败抛 RuntimeError(未连接/retcode 非 0),调用方(webhook 式降级/插件兜底)逻辑同 official。

作者: 李文煜
日期: 2026-08-16
"""
import base64
import logging

from adapter.reply_guard import sanitize_reply
from onebot import ws_client

logger = logging.getLogger(__name__)


class OnebotAdapter:
    """OneBot v11(NapCat 真人号)出站。"""

    async def send_text(self, oid: str, content: str, *, msg_id: str = "",
                        msg_seq: int = 1, human_authored: bool = False) -> dict:
        text = content if human_authored else sanitize_reply(content)
        # 审查#2(CQ 注入防护):message 用 array 格式,text 段不做 CQ 码解析——
        # 回复文本中的 [CQ:...] 字面量(用户诱导/引用)不会被 NapCat 解析成媒体/At。
        r = await ws_client.call_action("send_private_msg", {
            "user_id": int(oid),
            "message": [{"type": "text", "data": {"text": text}}],
        })
        if not r or r.get("status") != "ok":
            raise RuntimeError(f"onebot send_private_msg 失败: {r}")
        return {"delivered": True, "mode": "onebot_text", "response": r}

    async def send_voice(self, oid: str, silk_bytes: bytes, *, msg_id: str = "",
                         msg_seq: int = 1, content: str = "") -> dict:
        b64 = base64.b64encode(silk_bytes).decode()
        # array 格式:record 段(base64)+ 可选 text 附文段;text 段免 CQ 解析(同上)
        segs = []
        if content:
            segs.append({"type": "text", "data": {"text": content}})
        segs.append({"type": "record", "data": {"file": f"base64://{b64}"}})
        r = await ws_client.call_action("send_private_msg",
                                        {"user_id": int(oid), "message": segs})
        if not r or r.get("status") != "ok":
            raise RuntimeError(f"onebot 发语音失败: {r}")
        return {"delivered": True, "mode": "onebot_voice", "response": r}

    async def init(self) -> None:
        pass   # WS 通道由 ws_client 路由被动建立(NapCat 连入),无需主动初始化

    async def close(self) -> None:
        await ws_client.shutdown()
