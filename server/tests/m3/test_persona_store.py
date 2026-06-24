"""
人设存储（Redis + 文件双写）测试
验证 CRUD、默认人设 seed、对象绑定、导出

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 覆盖 persona.store 全部接口
"""
from persona import store
from persona.models import PersonaCard


async def test_set_and_get_with_file_double_write(fake_redis):
    card = PersonaCard(id="p1", name="测试", creator_notes="CN")
    await store.set_persona(fake_redis, card)
    got = await store.get_persona(fake_redis, "p1")
    assert got is not None and got.name == "测试"
    # 文件双写：index 含 p1
    assert "p1" in await fake_redis.smembers(store._K_INDEX)


async def test_delete(fake_redis):
    await store.set_persona(fake_redis, PersonaCard(id="p2", name="x"))
    existed = await store.delete_persona(fake_redis, "p2")
    assert existed is True
    assert await store.get_persona(fake_redis, "p2") is None


async def test_list_personas(fake_redis):
    await store.set_persona(fake_redis, PersonaCard(id="a", name="A"))
    await store.set_persona(fake_redis, PersonaCard(id="b", name="B"))
    cards = await store.list_personas(fake_redis)
    assert {c.id for c in cards} == {"a", "b"}


async def test_default_persona_seeded(fake_redis):
    card = await store.get_default_persona(fake_redis)
    assert card.id == "default"
    # seed 后 default 人设可查
    assert await store.get_persona(fake_redis, "default") is not None
    # 默认 id 键
    assert await fake_redis.get(store._K_DEFAULT) == "default"
    assert await fake_redis.get(store._K_PERSONA.format(pid="default")) != "default"  # 未被 id 键覆盖


async def test_object_persona_binding(fake_redis):
    await store.bind_object_persona(fake_redis, "obj1", "p1")
    assert await store.get_object_persona_id(fake_redis, "obj1") == "p1"


async def test_unbound_returns_active_default(fake_redis):
    # 未绑定返回 settings.persona_active_id（默认 "default"）
    assert await store.get_object_persona_id(fake_redis, "noobj") == "default"


async def test_export_roundtrip(fake_redis):
    await store.set_persona(fake_redis, PersonaCard(id="ex", name="导出", description="D"))
    data = await store.export_persona(fake_redis, "ex")
    assert data["data"]["name"] == "导出"
    assert "ex" in data["data"]["prompts"]


async def test_get_nonexistent_returns_none(fake_redis):
    assert await store.get_persona(fake_redis, "ghost") is None


async def test_save_avatar(fake_redis):
    """头像保存：落文件 + 更新人设 avatar 字段"""
    await store.get_default_persona(fake_redis)  # seed default 人设
    rel = await store.save_avatar(fake_redis, "default", b"\x89PNG fake", "png")
    assert rel == "static/avatar/default.png"
    card = await store.get_persona(fake_redis, "default")
    assert card.avatar == "static/avatar/default.png"


# V1.1 M9：嵌套字段往返 + 导出含新字段 + 快照回滚
from persona.models import Profile, Preferences, Relationship, DialogueExample


async def test_nested_fields_roundtrip(fake_redis):
    card = PersonaCard(id="n1", name="N", creator_notes="C",
                       profile=Profile(age="17", gender="女"),
                       preferences=Preferences(likes=["茶"]),
                       relationship=Relationship(relation="姐姐"),
                       example_dialogue=[DialogueExample(user="hi", character="嗨")])
    await store.set_persona(fake_redis, card)
    got = await store.get_persona(fake_redis, "n1")
    assert got.profile.age == "17" and got.profile.gender == "女"
    assert got.preferences.likes == ["茶"]
    assert got.relationship.relation == "姐姐"
    assert got.example_dialogue[0].character == "嗨"


async def test_export_contains_new_fields(fake_redis):
    card = PersonaCard(id="ex2", name="导出2",
                       profile=Profile(age="18"), preferences=Preferences(likes=["猫"]))
    await store.set_persona(fake_redis, card)
    data = await store.export_persona(fake_redis, "ex2")
    assert data["data"]["profile"]["age"] == "18"
    assert data["data"]["preferences"]["likes"] == ["猫"]


async def test_snapshot_and_rollback(fake_redis):
    await store.set_persona(fake_redis, PersonaCard(id="s1", name="原", creator_notes="原CN"))
    v1 = await store.snapshot_persona(fake_redis, "s1")
    assert v1 >= 1
    # 改人设后回滚到 v1（v1 快照内容是"原"）
    card = await store.get_persona(fake_redis, "s1")
    card.name = "改后"
    await store.set_persona(fake_redis, card)
    restored = await store.rollback_persona(fake_redis, "s1", v1)
    assert restored is not None
    assert restored.name == "原"


async def test_rollback_nonexistent_version(fake_redis):
    await store.set_persona(fake_redis, PersonaCard(id="s2", name="X"))
    assert await store.rollback_persona(fake_redis, "s2", 999) is None
