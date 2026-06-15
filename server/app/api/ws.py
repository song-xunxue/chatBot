"""
WebSocket 主通道端点（M1.5 tracer bullet）
当前实现：token 鉴权 + 接收 user_msg + 回显 ai_done，验证端到端通信
后续在此接入完整消息处理管道（见 02-架构 §4.2）

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.5 创建 WS 端点：token 鉴权 + user_msg 回显，打通 tracer bullet
"""
import sys
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# 引入跨端共享协议（shared 在项目根，加入 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.protocol import TYPE_USER_MSG, TYPE_AI_DONE, TYPE_ERROR, envelope, now_ts  # noqa: E402

from core.config import settings  # 同级导入：服务端配置


router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket 主通道：实时消息双向通信"""
    # 1.token 鉴权（单人场景）
    token = ws.query_params.get("token", "")
    if token != settings.access_token:
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
                # tracer bullet：直接回显，后续替换为完整管道处理
                text = data.get("payload", {}).get("text", "")
                reply = envelope(
                    TYPE_AI_DONE,
                    {"text": f"[echo] {text}"},
                    object_id=data.get("object_id", ""),
                    msg_id=f"ai_{now_ts()}",
                    ts=now_ts(),
                )
                await ws.send_json(reply)
            else:
                # 暂未处理的消息类型
                await ws.send_json(envelope(
                    TYPE_ERROR,
                    {"message": f"unsupported type: {msg_type}"},
                    ts=now_ts(),
                ))
    except WebSocketDisconnect:
        # 客户端正常断开
        pass
