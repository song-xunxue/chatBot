"""
user_alias 拟人化单测(2026-07-07):正则提取(自报模式+黑名单+语气词清洗) +
消息学习(倒序/user 优先) + renderer 全链路用 alias 替换"用户"。

作者: 李文煜
日期: 2026-07-07
"""
from llm.base import Message
from memory.user_alias import extract_user_alias, learn_user_alias_from_messages
from persona.models import PersonaCard, DialogueExample, Relationship
from persona.renderer import render_system_prompt


# ================ extract_user_alias 正则 ================

def test_extract_user_alias_patterns():
    """各种自报称呼模式命中(尾部语气词清洗)"""
    assert extract_user_alias("你可以叫我煜君") == "煜君"
    assert extract_user_alias("叫我小美吧") == "小美"      # 清洗尾部"吧"
    assert extract_user_alias("我叫清浔") == "清浔"
    assert extract_user_alias("我的名字是阿离") == "阿离"
    assert extract_user_alias("你可以喊我小明") == "小明"


def test_extract_user_alias_no_match():
    """无自报模式 → None"""
    assert extract_user_alias("今天天气真好") is None
    assert extract_user_alias("") is None
    assert extract_user_alias("用户喜欢动漫") is None


def test_extract_user_alias_blacklist():
    """黑名单词不返回(防误捕常见词)"""
    assert extract_user_alias("我叫外卖") is None       # "外卖"黑名单


# ================ learn_user_alias_from_messages 消息学习 ================

def test_learn_from_messages_recent_first():
    """倒序扫 user 消息,最近优先(后说的覆盖前面)"""
    msgs = [
        Message(role="user", content="叫我小名"),
        Message(role="assistant", content="好的"),
        Message(role="user", content="你可以叫我煜君"),   # 最近 user,取这个
    ]
    assert learn_user_alias_from_messages(msgs) == "煜君"


def test_learn_from_messages_dict():
    """支持 dict 形态消息(role/content 键)"""
    msgs = [{"role": "user", "content": "我叫阿离"}, {"role": "assistant", "content": "hi"}]
    assert learn_user_alias_from_messages(msgs) == "阿离"


def test_learn_from_messages_no_user():
    """无 user 消息 → None"""
    assert learn_user_alias_from_messages([Message(role="assistant", content="你好")]) is None
    assert learn_user_alias_from_messages([]) is None


# ================ renderer 全链路替换"用户"→user_alias ================

def test_renderer_replaces_user_label():
    """user_alias 非空 → 段标题/示例对话用 alias 代"用户"(拟人化)"""
    card = PersonaCard(id="p", user_alias="煜君", user_description="对方是学生",
                       relationship=Relationship(relation="青梅竹马"),
                       example_dialogue=[DialogueExample(user="在吗", character="在的")])
    prompt = render_system_prompt(card)
    assert "关于煜君" in prompt
    assert "与煜君的关系" in prompt
    assert "煜君:在吗" in prompt            # 示例对话用 alias
    assert "关于用户" not in prompt         # 不再用泛指"用户"


def test_renderer_fallback_user_label():
    """user_alias 空 → 回退"用户"(向后兼容)"""
    card = PersonaCard(id="p", user_description="对方是学生")
    prompt = render_system_prompt(card)
    assert "关于用户" in prompt
