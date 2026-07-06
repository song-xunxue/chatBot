"""
persona renderer【关于用户】段渲染单测(2026-07-05 面板改造):
验证 PersonaCard.user_description 字段被渲染为【关于用户】段注入 system_prompt。

作者: 李文煜
日期: 2026-07-05
"""
from persona.models import PersonaCard
from persona.renderer import render_system_prompt


def test_user_description_rendered():
    """user_description 非空 → system_prompt 含【关于用户】段"""
    card = PersonaCard(name="小聊", user_description="用户是大学生,喜欢动漫")
    prompt = render_system_prompt(card)
    assert "【关于用户】" in prompt
    assert "用户是大学生,喜欢动漫" in prompt


def test_user_description_empty_omitted():
    """user_description 空 → 不输出【关于用户】段(各段非空才输出)"""
    card = PersonaCard(name="小聊", user_description="")
    prompt = render_system_prompt(card)
    assert "【关于用户】" not in prompt


def test_output_contract_always_appended():
    """B-2:render_system_prompt 末尾恒带【输出契约】(无论 card 是否空、字段是否空)。
    根治"（轻声笑了）"类舞台指示 —— 契约禁止括号动作/旁白。"""
    # card 为空(兜底)也带契约
    assert "【输出契约】" in render_system_prompt(None)
    # 正常 card 末尾带契约,且契约在最后(在所有段之后)
    card = PersonaCard(name="小聊", user_description="用户喜欢动漫",
                       creator_notes="你是小聊")
    prompt = render_system_prompt(card)
    assert "【输出契约】" in prompt
    assert prompt.rfind("【输出契约】") > prompt.rfind("【关于用户】")   # 契约在关于用户段之后
    # 契约含禁止项(括号动作/旁白)
    assert "禁止" in prompt and "旁白" in prompt
