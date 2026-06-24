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
    # M3 新增（全部带默认值，保证向后兼容 / 降级 M2）
    user_id: str = ""                                   # 单人场景与 object_id 同
    persona_id: str = ""                                # 空则按 object_id 解析默认人设
    persona_card: object = None                         # PersonaCard，人设注入阶段填充
    memory_block: str = ""                              # 记忆协调器 render 输出，拼进 system_prompt 尾部
    recall_result: object = None                        # RecallResult，记忆检索阶段填充
    memory_meta: dict = field(default_factory=dict)     # hit_mids 等，供 save/编码使用
    turn_index: int = 0
    created_ts: int = 0                                 # ws.py 注入消息时间戳
    # M4 新增（插件系统）：默认空，保证向后兼容
    rich: dict = field(default_factory=dict)            # 富内容收集：on_after_llm 插件写入 audio/sticker/image 等
    plugin_meta: dict = field(default_factory=dict)     # 插件间协调用的临时状态暂存
