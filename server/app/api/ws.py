"""
WebSocket 主通道端点
token 鉴权 + 接收 user_msg + 走消息处理管道(run_stream) + 流式推送
ai_start/ai_chunk/ai_done。M2：把 M1.5 的 echo 回显替换为真实 LLM 流式回复。

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.5 创建 WS 端点：token 鉴权 + user_msg 回显，打通 tracer bullet

2026-06-19
变更说明：
  1. M2.4 接入消息处理管道：user_msg → run_stream → 流式 ai_start/ai_chunk/ai_done，替换 echo
  2. 无 LLM key 时降级提示；LLM 调用异常时回发 error

2026-06-24
变更说明：
  1. M4.1-review：run_stream 产出 0 chunk 且 reply_text 为空时回发 TYPE_ERROR（插件丢弃/空回复），避免客户端"转圈→空白"
"""
import sys
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# 引入跨端共享协议（shared 在项目根，加入 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.protocol import (  # noqa: E402
    TYPE_USER_MSG, TYPE_AI_START, TYPE_AI_CHUNK, TYPE_AI_DONE, TYPE_ERROR,
    TYPE_DELETE,
    envelope, now_ts,
)
from core.config import settings  # noqa: E402
from pipeline.context import MessageContext  # noqa: E402
from pipeline.runner import run_stream  # noqa: E402
from llm.registry import available_providers  # noqa: E402
from plugins import get_event_bus  # noqa: E402
from plugins.base import ON_DELETE  # noqa: E402
from plugins.connections import get_connection_registry  # noqa: E402


router = APIRouter()


def _build_ai_done_payload(ctx) -> dict:
    """构造 ai_done payload：文本 + 富内容(ctx.rich) + 状态(ctx.plugin_meta.mood)。
    抽出为模块级函数便于单测；客户端据此渲染图像/语音/心情。"""
    payload = {"text": ctx.reply_text}
    rich = getattr(ctx, "rich", None)
    if rich:
        payload["rich"] = rich
    mood = (getattr(ctx, "plugin_meta", None) or {}).get("mood")
    if mood:
        payload["state"] = {"mood": mood}
    return payload

# M2 默认 provider（M2.5 将改为按聊天对象绑定；此处优先用已配 key 的）
_DEFAULT_PROVIDER = "glm"


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket 主通道：实时消息双向通信"""
    # 1.token 鉴权（单人场景）；显式拒绝空 token，防 .env 误配为空时完全开放
    token = ws.query_params.get("token", "")
    if not settings.access_token or not token or token != settings.access_token:
        await ws.close(code=1008)  # 1008 = policy violation
        return

    # 2.接受连接
    await ws.accept()
    try:
        # 3.循环接收消息
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == TYPE_USER_MSG:
                await _handle_user_msg(ws, data)
            elif msg_type == TYPE_DELETE:
                # 删除=标记不符合人格，记 persona_evolve 负样本（仅落 pending，反推 M4）
                await _handle_delete(ws, data)
            else:
                # 暂未处理的消息类型
                await ws.send_json(envelope(
                    TYPE_ERROR,
                    {"message": f"unsupported type: {msg_type}"},
                    ts=now_ts(),
                ))
    except WebSocketDisconnect:
        # 客户端正常断开：注销连接
        get_connection_registry().deregister(ws)


async def _handle_user_msg(ws: WebSocket, data: dict) -> None:
    """处理用户消息：走管道流式生成回复，推 ai_start / ai_chunk(×N) / ai_done"""
    object_id = data.get("object_id", "")
    get_connection_registry().register(object_id, ws)   # 登记活跃连接，供主动推送
    text = data.get("payload", {}).get("text", "")

    # 无任何 LLM key 时降级提示（不崩）
    if not available_providers():
        await ws.send_json(envelope(
            TYPE_ERROR,
            {"message": "未配置任何 LLM API Key，请在 .env 填写 GLM/DEEPSEEK/SILICONFLOW"},
            object_id=object_id,
            ts=now_ts(),
        ))
        return

    ai_msg_id = f"ai_{now_ts()}"

    # ①ai_start：一条 AI 回复开始
    await ws.send_json(envelope(
        TYPE_AI_START,
        {"msg_id": ai_msg_id},
        object_id=object_id, msg_id=ai_msg_id, ts=now_ts(),
    ))

    # ②走管道流式；provider 默认 glm（M2.5 改为按聊天对象绑定）
    ctx = MessageContext(object_id=object_id, user_text=text,
                         provider_name=_DEFAULT_PROVIDER, created_ts=now_ts())
    sent_chunks = 0
    try:
        async for token in run_stream(ctx):
            sent_chunks += 1
            # ai_chunk：逐 token 推送（LLM 边产边推，降低首字延迟）
            await ws.send_json(envelope(
                TYPE_AI_CHUNK,
                {"delta": {"text": token}},
                object_id=object_id, msg_id=ai_msg_id, ts=now_ts(),
            ))
        if sent_chunks == 0 and not ctx.reply_text:
            if ctx.plugin_meta.get("held"):
                # 插件(如 reply_enhance)暂缓回复（攒够再回）：发 holding 指示，非错误
                await ws.send_json(envelope(
                    TYPE_AI_DONE,
                    {"text": "", "held": True},
                    object_id=object_id, msg_id=ai_msg_id, ts=now_ts(),
                ))
            else:
                # 插件在 on_message_in 丢弃消息或产生空回复：给客户端明确信号，避免"转圈→空白"
                await ws.send_json(envelope(
                    TYPE_ERROR,
                    {"message": "消息被插件丢弃或产生空回复"},
                    object_id=object_id, msg_id=ai_msg_id, ts=now_ts(),
                ))
        else:
            # ③ai_done：回复结束（附完整文本 + 富内容 rich + 状态 state，客户端渲染图像/语音/心情）
            await ws.send_json(envelope(
                TYPE_AI_DONE,
                _build_ai_done_payload(ctx),
                object_id=object_id, msg_id=ai_msg_id, ts=now_ts(),
            ))
    except Exception as e:
        # LLM 调用失败（网络/key 无效/限流）回发 error
        await ws.send_json(envelope(
            TYPE_ERROR,
            {"message": f"LLM 调用失败: {e}"},
            object_id=object_id, msg_id=ai_msg_id, ts=now_ts(),
        ))


async def _handle_delete(ws: WebSocket, data: dict) -> None:
    """处理删除消息：触发 on_delete 钩子(persona_evolve 消费人格负样本) + 记记忆负样本。
    失败仅记日志，不回发 error 以免打扰用户。on_delete 与记忆开关解耦（人格反推独立于记忆）"""
    object_id = data.get("object_id", "")
    payload = data.get("payload", {})
    bus = get_event_bus()
    if bus is not None:
        ctx = MessageContext(object_id=object_id, user_text="", reply_text="")
        ctx.plugin_meta["deleted_payload"] = payload
        await bus.fire(ON_DELETE, ctx)
    if not settings.memory_enabled:
        return
    try:
        from memory.coordinator import get_memory_coordinator
        coord = await get_memory_coordinator()
        await coord.record_negative_feedback(object_id, payload)
    except Exception:
        pass
