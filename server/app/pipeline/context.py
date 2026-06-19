"""
消息处理管道上下文 MessageContext
贯穿管道各阶段，承载用户消息、对话历史、人设 prompt、LLM 配置、产出回复等共享状态。

作者: 李文煜
日期: 2026-06-19

2026-06-19
变更说明：
  1. M2.2 创建 MessageContext：各阶段读写的共享数据载体
"""
from dataclasses import dataclass, field

from llm.base import Message


@dataclass
class MessageContext:
    """管道上下文：各阶段读写共享"""
    object_id: str                                      # 聊天对象 ID
    user_text: str = ""                                 # 用户本次消息文本
    history: list[Message] = field(default_factory=list)  # 对话历史（load_history 填充）
    system_prompt: str = ""                             # 人设 system prompt（persona_inject 填充，M2 占位）
    provider_name: str = "glm"                          # 使用的 LLM provider 名
    model: str = ""                                     # 模型名（空则用 provider 默认模型）
    # 产出
    reply_text: str = ""                                # 最终回复文本（llm_call 累积填充）
