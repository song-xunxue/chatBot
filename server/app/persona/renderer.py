"""
人设 system_prompt 渲染
把 PersonaCard 五维（creator_notes/description/personality/scenario）+ 动态状态
拼装为 LLM system prompt。对应 docs/06 §8 [system]+[state] 段、docs/09 §3.4。

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 创建 render_system_prompt
"""
from persona.models import PersonaCard, DynamicState


# 人设全空时的兜底 prompt（与 M2 固定 prompt 一致）
_DEFAULT_PROMPT = "你是一个友善的聊天助手，请自然、简洁地与用户对话。"


def render_system_prompt(card: PersonaCard | None,
                         state: DynamicState | None = None) -> str:
    """拼装人设 system prompt。
    card 为 None 或五维全空时回退默认 prompt；
    已设置 system_prompt 的上层逻辑由调用方保证（本函数只负责渲染）。
    """
    if card is None:
        return _DEFAULT_PROMPT
    parts = []
    if card.creator_notes:
        parts.append(f"【核心人设指令】\n{card.creator_notes}")
    if card.description:
        parts.append(f"【背景设定】\n{card.description}")
    if card.personality:
        parts.append(f"【性格】\n{card.personality}")
    if card.scenario:
        parts.append(f"【场景示例】\n{card.scenario}")
    st = state or card.dynamic_state
    if st and (st.mood or st.status):
        parts.append(f"【当前状态】心情:{st.mood} 状态:{st.status} 精力:{st.energy:.1f}")
    return "\n\n".join(parts) if parts else _DEFAULT_PROMPT
