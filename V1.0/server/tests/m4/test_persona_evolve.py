"""
persona_evolve 插件测试：删除负样本累积、达阈值产出提案(不自动改写人设)、样本队列清空。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.4 覆盖 persona_evolve：累积/阈值提案
"""
import json

from plugins.base import ON_DELETE


def _ctx(oid="o1", payload=None):
    c = type("C", (), {"object_id": oid, "user_text": "", "reply_text": "", "plugin_meta": {}})()
    if payload is not None:
        c.plugin_meta["deleted_payload"] = payload
    return c


async def test_accumulates_then_proposes(real_manager):
    await real_manager.load_all()
    await real_manager.set_global_enabled("persona_evolve", True)
    await real_manager.set_object_config("persona_evolve", "o1", True, {"threshold": 3})
    # 前 2 条：累积，未达阈值
    for i in range(2):
        c = _ctx(payload={"text": f"bad{i}"})
        await real_manager._bus.fire(ON_DELETE, c)
        assert c.plugin_meta.get("evolve_proposed") is not True
    samples = await real_manager._redis.get("mychat:persona_evolve:samples:o1")
    assert samples and len(json.loads(samples)) == 2
    # 第 3 条：达阈值 → 提案
    c3 = _ctx(payload={"text": "bad2"})
    await real_manager._bus.fire(ON_DELETE, c3)
    assert c3.plugin_meta.get("evolve_proposed") is True
    proposal = await real_manager._redis.get("mychat:persona_evolve:proposal:o1")
    assert proposal and len(json.loads(proposal)["samples"]) == 3
    # 样本队列已清空
    assert not await real_manager._redis.get("mychat:persona_evolve:samples:o1")


async def test_does_not_mutate_persona_directly(real_manager):
    """确认：仅产出提案，不自动改写人设(人工确认回路)"""
    await real_manager.load_all()
    await real_manager.set_global_enabled("persona_evolve", True)
    await real_manager.set_object_config("persona_evolve", "o1", True, {"threshold": 1})
    from persona import store as persona_store
    before = await persona_store.get_default_persona(real_manager._redis)
    await real_manager._bus.fire(ON_DELETE, _ctx(payload={"text": "bad"}))
    after = await persona_store.get_default_persona(real_manager._redis)
    # 人设未被自动改写（提案仅落 proposal 键）
    assert (before.id if before else None) == (after.id if after else None)
