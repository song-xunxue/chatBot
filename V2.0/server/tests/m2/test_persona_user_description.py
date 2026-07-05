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
