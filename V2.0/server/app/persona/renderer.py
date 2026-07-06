"""
人设 system_prompt 渲染
把 PersonaCard 各维度(creator_notes/description/user_description/personality/scenario
+ profile/preferences/relationship/example_dialogue) + 动态状态
拼装为 LLM system prompt。各段"非空才输出",段顺序固定。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 renderer 到 V2.0(零业务改动)

2026-07-05
变更说明：
  1. 面板改造:新增【关于用户】段(渲染 card.user_description),插入【喜好与厌恶】后、【与用户的关系】前

2026-07-06
变更说明：
  1. B-2 新增 OUTPUT_CONTRACT 常量 + render_system_prompt 末尾追加(根治"（轻声笑了）"类舞台指示)
"""
from persona.models import PersonaCard, DynamicState


# 人设全空时的兜底 prompt
_DEFAULT_PROMPT = "你是一个友善的聊天助手，请自然、简洁地与用户对话。"

# 输出契约(2026-07-06 B-2):强制自然对话,根治"（轻声笑了）"类舞台指示/旁白。
# render_system_prompt 末尾追加(基础覆盖所有调 render 的路径);pipeline.stage_build_messages
# 末尾再追加一次,成为 system prompt 最后一句,压制 mood prompt_hint / 记忆召回中的风格诱导。
OUTPUT_CONTRACT = (
    "\n\n【输出契约】\n"
    "你在用手机和对方发消息聊天。只输出你要发给对方的那句话本身,像微信打字一样自然。\n"
    "禁止用括号(全角（）或半角())、方括号、星号包裹动作、神态、心理或语气说明"
    "(不要出现如（轻声笑了）（微笑）（摸头）*叹气*这类描写)。\n"
    "不要旁白,不要解释自己正用什么语气说话,不要分点、列清单或加标题。"
)

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
      核心人设指令→背景设定→人物画像→性格→喜好与厌恶→关于用户→与用户的关系→开场白→场景示例→示例对话→当前状态。
    """
    if card is None:
        return _DEFAULT_PROMPT + OUTPUT_CONTRACT
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
    # 关于用户(对话另一方描述,让人设熟悉用户)
    if card.user_description:
        parts.append(f"【关于用户】\n{card.user_description}")
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
    body = "\n\n".join(parts) if parts else _DEFAULT_PROMPT
    return body + OUTPUT_CONTRACT
