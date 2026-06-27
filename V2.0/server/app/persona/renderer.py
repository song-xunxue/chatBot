"""
人设 system_prompt 渲染
把 PersonaCard 各维度(creator_notes/description/personality/scenario
+ profile/preferences/relationship/example_dialogue) + 动态状态
拼装为 LLM system prompt。各段"非空才输出",段顺序固定。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 renderer 到 V2.0(零业务改动)
"""
from persona.models import PersonaCard, DynamicState


# 人设全空时的兜底 prompt
_DEFAULT_PROMPT = "你是一个友善的聊天助手，请自然、简洁地与用户对话。"

# 示例对话渲染上限,防 prompt 膨胀与策略泄露
MAX_DIALOGUE_RENDER = 5
MAX_LINE_CHARS = 200


def _truncate(s: str, limit: int = MAX_LINE_CHARS) -> str:
    """超长截断加省略号"""
    s = s or ""
    return s if len(s) <= limit else s[:limit] + "…"


def _render_profile(profile) -> str:
    """人物画像段:只拼非空项,顿号连接"""
    items = []
    if profile.age:
        items.append(f"年龄:{profile.age}")
    if profile.gender:
        items.append(f"性别:{profile.gender}")
    if profile.occupation:
        items.append(f"职业/身份:{profile.occupation}")
    if profile.race:
        items.append(f"种族:{profile.race}")
    if profile.appearance:
        items.append(f"外貌:{profile.appearance}")
    if profile.speech_style:
        items.append(f"说话风格:{profile.speech_style}")
    if profile.catchphrase:
        items.append(f"口头禅:{profile.catchphrase}")
    return "、".join(items)


def _render_preferences(prefs) -> str:
    """喜好与厌恶段"""
    parts = []
    if prefs.likes:
        parts.append("喜欢:" + "、".join(prefs.likes))
    if prefs.dislikes:
        parts.append("厌恶:" + "、".join(prefs.dislikes))
    return "\n".join(parts)


def _render_dialogue(examples: list) -> str:
    """示例对话段:渲染前 MAX_DIALOGUE_RENDER 条,每条 user/character 截断"""
    lines = []
    for ex in examples[:MAX_DIALOGUE_RENDER]:
        u = getattr(ex, "user", "") or ""
        c = getattr(ex, "character", "") or ""
        if not u and not c:
            continue
        lines.append(f"用户:{_truncate(u)}\n角色:{_truncate(c)}")
    return "\n\n".join(lines)


def render_system_prompt(card: PersonaCard | None,
                         state: DynamicState | None = None) -> str:
    """拼装人设 system prompt。
    card 为 None 或全空时回退默认 prompt;各段"非空才输出",段顺序固定:
      核心人设指令→背景设定→人物画像→性格→喜好与厌恶→与用户的关系→开场白→场景示例→示例对话→当前状态。
    """
    if card is None:
        return _DEFAULT_PROMPT
    parts = []
    if card.creator_notes:
        parts.append(f"【核心人设指令】\n{card.creator_notes}")
    if card.description:
        parts.append(f"【背景设定】\n{card.description}")
    prof_txt = _render_profile(card.profile)
    if prof_txt:
        parts.append(f"【人物画像】\n{prof_txt}")
    if card.personality:
        parts.append(f"【性格】\n{card.personality}")
    pref_txt = _render_preferences(card.preferences)
    if pref_txt:
        parts.append(f"【喜好与厌恶】\n{pref_txt}")
    # 与用户的关系(只渲染 relation;greeting 单独成段)
    if card.relationship and card.relationship.relation:
        parts.append(f"【与用户的关系】\n{card.relationship.relation}")
    # 开场白(单独成段,只渲染一次)
    if card.relationship and card.relationship.greeting:
        parts.append(f"【开场白】\n{card.relationship.greeting}")
    if card.scenario:
        parts.append(f"【场景示例】\n{card.scenario}")
    if card.example_dialogue:
        dlg_txt = _render_dialogue(card.example_dialogue)
        if dlg_txt:
            parts.append(f"【示例对话】\n{dlg_txt}")
    st = state or card.dynamic_state
    if st and (st.mood or st.status):
        parts.append(f"【当前状态】心情:{st.mood} 状态:{st.status} 精力:{st.energy:.1f}")
    return "\n\n".join(parts) if parts else _DEFAULT_PROMPT
