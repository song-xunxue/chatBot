"""
默认人设 seed
未绑定人设或人设缺失时使用的通用友善助手卡。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植默认人设 seed 到 V2.0(零业务改动)
"""
from persona.models import PersonaCard


def default_persona() -> PersonaCard:
    """默认人设:通用友善助手"""
    return PersonaCard(
        id="default",
        name="小聊",
        description="一个陪伴用户聊天的助手。",
        personality="友善、自然、简洁。",
        creator_notes="你是一个友善的聊天助手，请自然、简洁地与用户对话。",
    )
