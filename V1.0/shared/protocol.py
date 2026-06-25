"""
跨端共享协议：消息类型常量与信封结构
客户端与服务端共用，保证 WS 消息格式一致（对应 03-接口设计 §3）

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.5 定义 WS 消息类型常量、信封构建与时间戳辅助函数
"""
import time

# ===== 入站事件类型（客户端 -> 服务端）=====
TYPE_USER_MSG = "user_msg"      # 用户发送消息
TYPE_PRESENCE = "presence"      # 在线/输入状态
TYPE_RECALL = "recall"          # 撤回（仅用户自己的消息）
TYPE_DELETE = "delete"          # 删除（标记不符合人格，作负反馈）
TYPE_SYNC_REQ = "sync_req"      # 请求增量同步

# ===== 出站事件类型（服务端 -> 客户端）=====
TYPE_AI_START = "ai_start"          # 一条 AI 回复开始（流式）
TYPE_AI_CHUNK = "ai_chunk"          # 流式增量分片
TYPE_AI_DONE = "ai_done"            # 回复结束 + 最新状态
TYPE_STATE_UPDATE = "state_update"  # 主动状态变更（动态心情）
TYPE_NUDGE = "nudge"                # 触发桌宠抖动
TYPE_SYNC_RESP = "sync_resp"        # 增量同步返回
TYPE_PROACTIVE_MSG = "proactive_msg"  # 聊天对象自主发消息
TYPE_ERROR = "error"                # 错误

# ===== V1.1 M13 代人聊天 B 实时接管 =====
TYPE_TAKEOVER_REQUEST = "takeover_request"      # 出站：代答请求（推面板）
TYPE_TAKEOVER_RESOLVED = "takeover_resolved"    # 出站：代答已完成（推面板，前端移除待答项）
TYPE_TAKEOVER_PENDING = "takeover_pending"      # 出站：客户端等待人工代答（服务端主动，非客户端自计时）
TYPE_TAKEOVER_TIMEOUT = "takeover_timeout"      # 出站：代答超时（服务端主动）
TYPE_TAKEOVER_SUBSCRIBE = "takeover_subscribe"  # 入站：面板订阅代答请求流


def now_ts() -> int:
    """当前 Unix 毫秒时间戳"""
    return int(time.time() * 1000)


def envelope(msg_type: str, payload: dict, object_id: str = "", msg_id: str = "", ts: int = 0) -> dict:
    """构建 WS 消息信封（对应 03-接口设计 §3.1）"""
    return {
        "type": msg_type,
        "object_id": object_id,
        "msg_id": msg_id,
        "payload": payload,
        "ts": ts if ts else now_ts(),
    }


def user_msg(text: str, object_id: str = "default", ts: int = 0) -> dict:
    """构建用户消息（入站便捷函数）"""
    return envelope(TYPE_USER_MSG, {"text": text}, object_id=object_id, ts=ts)
