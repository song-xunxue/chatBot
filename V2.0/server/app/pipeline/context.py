"""
消息处理管道上下文 MessageContext
贯穿管道各阶段,承载用户消息、对话历史、人设 prompt、LLM 配置、mood、产出回复等共享状态。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 MessageContext 到 V2.0;新增 mood_value 字段(stage_mood 填充)

2026-06-28
变更说明：
  1. M3 新增 reply_mid 字段(stage_save 填 ai 消息 mid,stage_score 评分定位用)
"""
from dataclasses import dataclass, field

from llm.base import Message


@dataclass
class MessageContext:
    """管道上下文:各阶段读写共享"""
    object_id: str                                      # 聊天对象 ID(QQ 私聊场景 = user_openid)
    user_text: str = ""                                 # 用户本次消息文本
    history: list[Message] = field(default_factory=list)  # 对话历史(load_history 填充)
    system_prompt: str = ""                             # 人设 system prompt(persona_inject 填充)
    provider_name: str = "glm"                          # 使用的 LLM provider 名
    model: str = ""                                     # 模型名(空则用 provider 默认模型)
    # 产出
    reply_text: str = ""                                # 最终回复文本(llm_stream 累积填充)
    reply_mid: str = ""                                 # ai 回复消息 mid(stage_save 填,stage_score 评分定位)
    # 人设/记忆
    user_id: str = ""                                   # 单人场景与 object_id 同
    persona_id: str = ""                                # 空则按 object_id 解析默认人设
    persona_card: object = None                         # PersonaCard,人设注入阶段填充
    memory_block: str = ""                              # 记忆协调器 render 输出,拼进 system_prompt 尾部
    recall_result: object = None                        # RecallResult,记忆检索阶段填充
    memory_meta: dict = field(default_factory=dict)     # hit_mids 等,供 save/编码使用
    turn_index: int = 0
    created_ts: int = 0                                 # 消息时间戳(webhook 注入)
    # mood(stage_mood_inject 填充)
    mood_value: float = 0.5                             # 当前 mood 值[0,1],0.5 中性
    # 富内容/插件协调
    rich: dict = field(default_factory=dict)            # 富内容收集(M6 多模态插件写入)
    plugin_meta: dict = field(default_factory=dict)     # 插件/stage 间协调状态(mood label/kaomoji 等)
