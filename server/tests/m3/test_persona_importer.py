"""
人设 JSON 导入兼容测试
验证嵌套/扁平/最小/avatar_path 剥离/自动 id

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 覆盖 parse_persona_json
"""
from persona.importer import parse_persona_json


def test_import_nested_form():
    raw = {"data": {"prompts": {"160cabec": {"data": {
        "name": "雷姆", "description": "D", "personality": "P",
        "scenario": "S", "creator_notes": "C"}}}}}
    card = parse_persona_json(raw)
    assert card.id == "160cabec"
    assert card.name == "雷姆"
    assert card.creator_notes == "C"


def test_import_nested_key_with_apostrophe():
    # 真实样例 persona_林挽夏.json 的 prompts key 是 "shuoshuo's prompt"
    raw = {"data": {"prompts": {"shuoshuo's prompt": {"data": {"name": "林挽夏"}}}}}
    card = parse_persona_json(raw)
    assert card.id == "shuoshuo's prompt"
    assert card.name == "林挽夏"


def test_import_nested_avatar_path_stripped():
    raw = {"data": {"prompts": {"k1": {"data": {
        "name": "X", "avatar_path": "C:/a/b/img.png"}}}}}
    card = parse_persona_json(raw)
    # 剥离绝对路径，只留文件名，落到 static/avatar/{id}/
    assert card.avatar == "static/avatar/k1/img.png"


def test_import_flat_form():
    raw = {"data": {"name": "扁平", "description": "D", "personality": "P"}}
    card = parse_persona_json(raw)
    assert card.name == "扁平"
    assert card.description == "D"


def test_import_minimal_no_crash():
    raw = {"data": {"prompts": {"k2": {"data": {"name": "最小"}}}}}
    card = parse_persona_json(raw)
    assert card.name == "最小"
    assert card.personality == ""  # 缺失字段不报错


def test_import_auto_id_when_missing():
    raw = {"data": {"name": "无id"}}
    card = parse_persona_json(raw)
    assert card.id.startswith("persona_")  # 自动生成


def test_import_explicit_id_overrides():
    raw = {"data": {"prompts": {"inner": {"data": {"name": "X"}}}}}
    card = parse_persona_json(raw, persona_id="my-id")
    assert card.id == "my-id"  # 显式传入优先


# V1.1 M9：新字段导入（嵌套/扁平两形态兼容）
def test_import_nested_profile():
    raw = {"data": {"prompts": {"k1": {"data": {
        "name": "X", "profile": {"age": "18", "gender": "女", "catchphrase": "喵"}}}}}}
    card = parse_persona_json(raw)
    assert card.profile.age == "18"
    assert card.profile.gender == "女"
    assert card.profile.catchphrase == "喵"


def test_import_flat_profile():
    raw = {"data": {"name": "X", "age": "20", "gender": "男", "speech_style": "温柔"}}
    card = parse_persona_json(raw)
    assert card.profile.age == "20"
    assert card.profile.gender == "男"
    assert card.profile.speech_style == "温柔"


def test_import_preferences_relationship_dialogue():
    raw = {"data": {"prompts": {"k": {"data": {
        "name": "X", "preferences": {"likes": ["猫"]},
        "relationship": {"relation": "主仆", "greeting": "主人~"},
        "example_dialogue": [{"user": "你好", "character": "嗨"}]}}}}}
    card = parse_persona_json(raw)
    assert card.preferences.likes == ["猫"]
    assert card.relationship.relation == "主仆"
    assert card.relationship.greeting == "主人~"
    assert card.example_dialogue[0].user == "你好"


def test_import_old_json_new_fields_default():
    raw = {"data": {"prompts": {"k": {"data": {"name": "旧"}}}}}
    card = parse_persona_json(raw)
    assert card.profile.age == ""
    assert card.preferences.likes == []
    assert card.example_dialogue == []
