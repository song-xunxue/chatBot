"""
默认人设 seed
M2 阶段的固定 prompt 降级为一张默认人设卡，未绑定人设或人设缺失时使用。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 创建默认人设 seed（等价于 M2 固定 prompt）
"""
from persona.models import PersonaCard


def default_persona() -> PersonaCard:
    """默认人设：通用友善助手（M2 固定 prompt 的等价物）"""
    return PersonaCard(
        id="default",
        name="小聊",
        description="一个陪伴用户聊天的助手。",
        personality="友善、自然、简洁。",
        creator_notes="你是一个友善的聊天助手，请自然、简洁地与用户对话。",
    )
