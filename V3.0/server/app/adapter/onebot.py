"""
onebot 适配器(V3.0 M-V3-1):经 NapCat 反向 WS 发 OneBot v11 Action。
出站通道由 onebot/ws_client 维护(NapCat 主动连入的 WS 连接);本适配器只发 Action + 等响应。

- 文本:send_private_msg;出站守卫与 official 同构(human_authored=False 过 sanitize_reply,架构 #3)。
- 语音:CQ record 码 + base64(silk;QQ 语音统一格式,NapCat 直接下发音 Voice 条)。
- msg_id/msg_seq 忽略(OneBot 个人号无被动回复窗口/月配额概念,主动直发)。
- 失败抛 RuntimeError(未连接/retcode 非 0),调用方(webhook 式降级/插件兜底)逻辑同 official。
- 表情包(2026-09-15):文本中 [表情包: 描述] token → sticker_store.find_sticker 库匹配 →
  image 段(base64)发真实表情包;未匹配 token 保留字面文本(透明可排查,不静默丢)。
  覆盖所有 send_text 路径(pipeline 下发/分段插件每段/面板代答主动发送),管理员在面板
  发 token 亦可发真实表情包。
- 表情包独立成条(2026-09-15 #2,用户习惯反馈):表情包不与文本混发同一条消息——
  文本(若有)一条、每个表情包各一条,分开 send_private_msg,条间随机 0.4~0.9s 拟人间隔。

作者: 李文煜
日期: 2026-08-16

2026-09-15
变更说明：
    1. send_text 表情包 token 翻译(收发功能;segment array 天然支持 image 段)
    2. 表情包独立成条:文本与表情包拆成多次独立 send(聊天习惯),条间随机小延迟
"""
import asyncio
import base64
import logging
import random

from adapter.reply_guard import sanitize_reply
from onebot import ws_client

logger = logging.getLogger(__name__)

# 表情包独立成条后的条间延迟区间(秒):拟人连发节奏,同 continuous_send 分段间隔同量级
STICKER_SEND_DELAY = (0.4, 0.9)


class OnebotAdapter:
    """OneBot v11(NapCat 真人号)出站。"""

    async def send_text(self, oid: str, content: str, *, msg_id: str = "",
                        msg_seq: int = 1, human_authored: bool = False) -> dict:
        text = content if human_authored else sanitize_reply(content)
        # 审查#2(CQ 注入防护):message 用 array 格式,text 段不做 CQ 码解析——
        # 回复文本中的 [CQ:...] 字面量(用户诱导/引用)不会被 NapCat 解析成媒体/At。
        # [表情包: x] token 翻译成独立 image 消息(表情包单独成条,不与文本混发)
        messages = await self._build_messages(text)
        r = None
        for i, segs in enumerate(messages):
            if i:
                await asyncio.sleep(random.uniform(*STICKER_SEND_DELAY))
            r = await ws_client.call_action("send_private_msg", {
                "user_id": int(oid),
                "message": segs,
            })
            if not r or r.get("status") != "ok":
                raise RuntimeError(f"onebot send_private_msg 失败: {r}")
        return {"delivered": True, "mode": "onebot_text", "response": r}

    @staticmethod
    async def _build_messages(text: str) -> list[list[dict]]:
        """文本 → 独立消息列表(每条 = OneBot 段数组):文本 run 一条 +
        每个 [表情包: 描述] token 各一条(image 段)。token 未匹配库文件时保留字面文本
        (透明,便于排查描述偏差);软失败不影响文本发送;无 token = 单条纯文本。"""
        from storage import sticker_store
        from storage.redis_client import get_redis
        try:
            redis = await get_redis()
            parts: list[list[dict]] = []           # 独立消息列表
            text_run: list[str] = []               # 文本片段累积(合成一条)

            def _flush_text() -> None:
                joined = "".join(text_run).strip("\n")   # 去条边界的换行(token 分隔的排版产物)
                if joined:
                    parts.append([{"type": "text", "data": {"text": joined}}])
                text_run.clear()

            for kind, val in sticker_store.split_reply_with_tokens(text):
                if kind == "text":
                    if val:
                        text_run.append(val)
                    continue
                path = await sticker_store.find_sticker(redis, val)
                if path is not None:
                    b64 = base64.b64encode(sticker_store.read_bytes(path)).decode()
                    _flush_text()                  # 表情包前先把累积文本成条
                    parts.append([{"type": "image", "data": {"file": f"base64://{b64}"}}])
                    logger.info("表情包下发(独立成条): %s -> %s", val, path.name)
                else:
                    logger.info("表情包未匹配库,保留字面文本: %s", val)
                    text_run.append(f"[表情包: {val}]")
            _flush_text()
            if not parts:
                parts = [[{"type": "text", "data": {"text": text}}]]
            return parts
        except Exception:
            logger.exception("表情包消息构建失败(回退纯文本)")
            return [[{"type": "text", "data": {"text": text}}]]

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
