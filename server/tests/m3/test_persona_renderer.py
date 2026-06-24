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
