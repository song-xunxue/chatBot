"""
人设 system_prompt 渲染测试
验证 render_system_prompt 的五维拼装、动态状态、空兜底

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 覆盖 render_system_prompt
"""
from persona.renderer import render_system_prompt
from persona.models import PersonaCard, DynamicState


def test_render_none_returns_default():
    assert "友善" in render_system_prompt(None)


def test_render_empty_card_returns_default():
    assert "友善" in render_system_prompt(PersonaCard())


def test_render_full_five_dims():
    card = PersonaCard(
        creator_notes="你是猫娘", description="背景X",
        personality="温柔", scenario="场景Y",
    )
    out = render_system_prompt(card)
    assert "【核心人设指令】" in out and "你是猫娘" in out
    assert "【背景设定】" in out and "背景X" in out
    assert "【性格】" in out and "温柔" in out
    assert "【场景示例】" in out and "场景Y" in out


def test_render_with_explicit_dynamic_state():
    card = PersonaCard(creator_notes="X")
    out = render_system_prompt(card, DynamicState(mood="开心", status="宅", energy=0.5))
    assert "【当前状态】" in out and "开心" in out and "宅" in out


def test_render_state_skipped_when_empty():
    card = PersonaCard(creator_notes="X")
    out = render_system_prompt(card)
    assert "【当前状态】" not in out


# V1.1 M9：新字段渲染
from persona.models import Profile, Preferences, Relationship, DialogueExample


def test_render_profile_section():
    card = PersonaCard(creator_notes="X", profile=Profile(age="16岁", gender="女", speech_style="温柔"))
    out = render_system_prompt(card)
    assert "【人物画像】" in out
    assert "年龄:16岁" in out and "性别:女" in out and "说话风格:温柔" in out


def test_render_preferences_section():
    card = PersonaCard(creator_notes="X", preferences=Preferences(likes=["猫", "甜食"], dislikes=["早起"]))
    out = render_system_prompt(card)
    assert "【喜好与厌恶】" in out
    assert "喜欢:猫、甜食" in out and "厌恶:早起" in out


def test_render_relationship_and_greeting():
    card = PersonaCard(creator_notes="X", relationship=Relationship(relation="青梅竹马", greeting="嗨~"))
    out = render_system_prompt(card)
    assert "【与用户的关系】" in out and "青梅竹马" in out
    assert "【开场白】" in out and "嗨~" in out


def test_render_example_dialogue():
    card = PersonaCard(creator_notes="X", example_dialogue=[
        DialogueExample(user="你好", character="嗨~"),
        DialogueExample(user="在吗", character="在的哦"),
    ])
    out = render_system_prompt(card)
    assert "【示例对话】" in out
    assert "用户:你好" in out and "角色:嗨~" in out


def test_render_empty_new_fields_no_section():
    card = PersonaCard(creator_notes="X")  # 新字段全空：不输出新段（旧卡逐字节兼容）
    out = render_system_prompt(card)
    for sec in ("【人物画像】", "【喜好与厌恶】", "【与用户的关系】", "【开场白】", "【示例对话】"):
        assert sec not in out


def test_render_dialogue_truncation():
    long_u = "啊" * 300
    card = PersonaCard(creator_notes="X", example_dialogue=[DialogueExample(user=long_u, character="c")])
    out = render_system_prompt(card)
    assert "…" in out   # 超长截断标记
