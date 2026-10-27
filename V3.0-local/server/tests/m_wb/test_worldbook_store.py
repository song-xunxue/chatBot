"""
worldbook_store 存储层单测(fakeredis):CRUD roundtrip(keys JSON 化)/部分更新保留字段/
删除清索引/by_ref 幂等/注入记账+跨日滚动/统计/自动同步(memory 幂等、diary→dream 分流、
core→always、episodic→summary)/遗忘恢复同步/rebuild 幂等与 manual 保留/dry-run 不写。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新增:存储层全路径单测
"""
import time

from memory import worldbook_store
from memory.models import MemoryItem, CoreFact, EpisodicEntry
from memory.worldbook import WbEntry


def _e(eid="wb_x", **kw) -> WbEntry:
    d = dict(id=eid, title="标题", content="内容", keys=["打雷"], mode="trigger")
    d.update(kw)
    return WbEntry(**d)


# ================ CRUD ================

async def test_upsert_get_roundtrip(fake_redis):
    """写读 roundtrip:list 字段 JSON 化后可完整还原"""
    e = _e(keys=["打雷", "雷声"], secondary_keys=["晚上"])
    await worldbook_store.upsert_entry(fake_redis, e)
    back = await worldbook_store.get_entry(fake_redis, e.id)
    assert back.keys == ["打雷", "雷声"]
    assert back.secondary_keys == ["晚上"]
    assert back.title == "标题" and back.content == "内容"
    assert await worldbook_store.get_entry(fake_redis, "wb_none") is None


async def test_list_entries_filter_and_order(fake_redis):
    """created 倒序 + source/enabled 过滤 + limit 截断"""
    e1 = _e("wb_1", source="manual", created_ts=1000)
    e2 = _e("wb_2", source="memory", enabled=False, created_ts=2000)
    e3 = _e("wb_3", source="memory", created_ts=3000)
    for e in (e1, e2, e3):
        await worldbook_store.upsert_entry(fake_redis, e)
    assert [e.id for e in await worldbook_store.list_entries(fake_redis)] == \
        ["wb_3", "wb_2", "wb_1"]                                   # created 倒序
    assert [e.id for e in await worldbook_store.list_entries(fake_redis, source="memory")] == \
        ["wb_3", "wb_2"]
    assert [e.id for e in await worldbook_store.list_entries(fake_redis, enabled=False)] == ["wb_2"]
    assert len(await worldbook_store.list_entries(fake_redis, limit=2)) == 2


async def test_update_entry_partial(fake_redis):
    """部分更新:只改出现字段,其余保留;content 变化重算 token_estimate"""
    e = _e("wb_u", content="打雷时她会缩起来", order=100, probability=0.6)
    await worldbook_store.upsert_entry(fake_redis, e)
    got = await worldbook_store.update_entry(fake_redis, "wb_u",
                                             {"content": "打雷时她会缩在被子里",
                                              "probability": 0.9, "enabled": False})
    assert got.content == "打雷时她会缩在被子里"
    assert got.probability == 0.9 and got.enabled is False
    assert got.order == 100                                  # 未出现在 patch,保留
    assert got.token_estimate > 0
    assert await worldbook_store.update_entry(fake_redis, "wb_none", {"title": "x"}) is None


async def test_delete_entry_clears_indexes(fake_redis):
    """物理删除:hash/ids/by_key/by_ref 全清"""
    e = _e("wb_d", keys=["打雷"], source="memory", source_ref="o1:m1")
    await worldbook_store.upsert_entry(fake_redis, e)
    assert await worldbook_store.delete_entry(fake_redis, "wb_d") is True
    assert await worldbook_store.get_entry(fake_redis, "wb_d") is None
    assert await worldbook_store.list_entries(fake_redis) == []
    assert await fake_redis.smembers("mychat:wb:by_key:打雷") == set()
    assert await fake_redis.get("mychat:wb:by_ref:memory:o1:m1") is None
    assert await worldbook_store.delete_entry(fake_redis, "wb_d") is False


async def test_upsert_by_key_index_refresh(fake_redis):
    """改 keys 后旧 by_key 索引清、新索引建"""
    e = _e("wb_k", keys=["打雷"])
    await worldbook_store.upsert_entry(fake_redis, e)
    e.keys = ["下雨"]
    await worldbook_store.upsert_entry(fake_redis, e)
    assert await fake_redis.smembers("mychat:wb:by_key:打雷") == set()
    assert await fake_redis.smembers("mychat:wb:by_key:下雨") == {"wb_k"}


async def test_find_by_ref(fake_redis):
    """by_ref 索引:写入后可按 (source, source_ref) 找回条目(幂等 upsert 的查询入口;
    同步路径幂等语义由 sync_from_memory 保证——先 find 再复用 id)"""
    e = _e("wb_r1", source="memory", source_ref="o1:m1")
    await worldbook_store.upsert_entry(fake_redis, e)
    found = await worldbook_store.find_by_ref(fake_redis, "memory", "o1:m1")
    assert found is not None and found.id == "wb_r1"
    assert await worldbook_store.find_by_ref(fake_redis, "memory", "nope") is None
    assert await worldbook_store.find_by_ref(fake_redis, "", "o1:m1") is None


# ================ 记账 / 统计 ================

async def test_record_injection_and_hit(fake_redis):
    """注入 hits+1+双时间戳;命中未注入只刷 last_hit_at"""
    e = _e("wb_i")
    await worldbook_store.upsert_entry(fake_redis, e)
    await worldbook_store.record_hit(fake_redis, [e.id])
    got = await worldbook_store.get_entry(fake_redis, e.id)
    assert got.hits == 0 and got.last_hit_at > 0 and got.last_injected_at == 0
    await worldbook_store.record_injection(fake_redis, [e.id], tokens=42)
    got = await worldbook_store.get_entry(fake_redis, e.id)
    assert got.hits == 1 and got.last_injected_at >= got.last_hit_at


async def test_stats_day_rollover(fake_redis):
    """stats 累计 + 跨日滚动(day_injections 清零重计)"""
    e = _e("wb_s")
    await worldbook_store.upsert_entry(fake_redis, e)
    await worldbook_store.record_injection(fake_redis, [e.id], tokens=100)
    await worldbook_store.record_injection(fake_redis, [e.id], tokens=50)
    s = await worldbook_store.get_stats(fake_redis)
    assert s["total"] == 1 and s["enabled"] == 1 and s["always"] == 0
    assert s["today_injections"] == 2 and s["avg_tokens"] == 75.0
    assert s["by_source"] == {"manual": 1}
    # 伪造跨日:stat_day 改成昨天再注入,day_* 应清零重计
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86_400 * 2))
    await fake_redis.hset("mychat:wb:stats", "stat_day", yesterday)
    await worldbook_store.record_injection(fake_redis, [e.id], tokens=10)
    s2 = await worldbook_store.get_stats(fake_redis)
    assert s2["today_injections"] == 1 and s2["avg_tokens"] == round(160 / 3, 1)


# ================ 自动同步 ================

def _mem(mid="m1", **kw) -> MemoryItem:
    d = dict(id=mid, content="她怕打雷", importance=0.8, useful_score=0.7,
             source="dialog", tags=[])
    d.update(kw)
    return MemoryItem(**d)


async def test_sync_from_memory_create_and_idempotent(fake_redis):
    """新建条目(source=memory,keys 自动提取,weight=useful_score)+ 幂等刷新不重复建"""
    m = _mem()
    e1 = await worldbook_store.sync_from_memory(fake_redis, "10001", m)
    assert e1.source == "memory" and e1.source_ref == "10001:m1"
    assert e1.mode == "trigger" and e1.enabled is True
    assert e1.weight == 0.7
    assert any("打雷" in k for k in e1.keys)
    # 幂等:同 mid 再同步 → 更新既有条目,不新建
    m2 = _mem(content="她非常怕打雷会哭", useful_score=0.9)
    e2 = await worldbook_store.sync_from_memory(fake_redis, "10001", m2)
    assert e2.id == e1.id
    assert e2.content == "她非常怕打雷会哭" and e2.weight == 0.9
    assert len(await worldbook_store.list_entries(fake_redis)) == 1


async def test_sync_from_memory_source_mapping(fake_redis):
    """source 映射:diary(tags 含 dream)→dream / diary→diary / roleplay→roleplay /
    其余(dialog/manual/extract/proxy)→memory"""
    cases = [
        (_mem("m_a", source="diary", tags=["dream", "2026-10-26"]), "dream"),
        (_mem("m_b", source="diary", tags=["diary", "2026-10-26"]), "diary"),
        (_mem("m_c", source="roleplay"), "roleplay"),
        (_mem("m_d", source="manual"), "memory"),
    ]
    for m, expect in cases:
        e = await worldbook_store.sync_from_memory(fake_redis, "10001", m)
        assert e.source == expect, f"{m.source}->{e.source} 应为 {expect}"


async def test_sync_from_memory_forgotten_disabled(fake_redis):
    """遗忘态记忆同步为 enabled=False"""
    e = await worldbook_store.sync_from_memory(fake_redis, "10001", _mem(forgotten=True))
    assert e.enabled is False


async def test_sync_core_fact_always(fake_redis):
    """core 事实 → mode=always 常驻条目,幂等"""
    f = CoreFact(key="user_name", content="他叫主人")
    e = await worldbook_store.sync_core_fact(fake_redis, "10001", f)
    assert e.mode == "always" and e.source_ref == "core:10001:user_name"
    assert e.enabled is True
    e2 = await worldbook_store.sync_core_fact(fake_redis, "10001", CoreFact(key="user_name", content="他叫小煜"))
    assert e2.id == e.id and e2.content == "他叫小煜"
    assert len(await worldbook_store.list_entries(fake_redis)) == 1


async def test_sync_episodic(fake_redis):
    """情景摘要 → source=summary 条目,幂等"""
    ep = EpisodicEntry(id="epi_12", summary="聊了打雷和看海的事",
                       span_start_ts=0, span_end_ts=0)
    e = await worldbook_store.sync_episodic(fake_redis, "10001", ep)
    assert e.source == "summary" and e.source_ref == "epi:10001:epi_12"
    assert e.probability == 0.7
    e2 = await worldbook_store.sync_episodic(
        fake_redis, "10001",
        EpisodicEntry(id="epi_12", summary="改:聊了打雷", span_start_ts=0, span_end_ts=0))
    assert e2.id == e.id and e2.content == "改:聊了打雷"


async def test_sync_forget_and_restore(fake_redis):
    """遗忘→enabled=False,恢复→True(经 mark_forgotten 全路径收口)"""
    m = _mem()
    await worldbook_store.sync_from_memory(fake_redis, "10001", m)
    await worldbook_store.sync_forget(fake_redis, "10001", [m.id], True)
    assert (await worldbook_store.list_entries(fake_redis))[0].enabled is False
    await worldbook_store.sync_forget(fake_redis, "10001", [m.id], False)
    assert (await worldbook_store.list_entries(fake_redis))[0].enabled is True


# ================ rebuild ================

async def test_rebuild_auto_idempotent_keeps_manual(fake_redis):
    """rebuild:自动来源全删重建(幂等),manual 保留;遗忘记忆→disabled"""
    from memory import store as mem_store
    await mem_store.upsert_long_term(fake_redis, "10001", _mem("m1"))
    await mem_store.upsert_long_term(fake_redis, "10001", _mem("m2", forgotten=True))
    await mem_store.set_core(fake_redis, "10001", [CoreFact(key="k", content="核心事实")])
    await mem_store.append_episodic(fake_redis, "10001",
                                    EpisodicEntry(id="epi_1", summary="摘要内容",
                                                  span_start_ts=0, span_end_ts=0))
    await worldbook_store.upsert_entry(fake_redis, _e("wb_keep", source="manual"))
    r1 = await worldbook_store.rebuild_auto(fake_redis, ["10001"])
    assert r1["created"] == 3 and r1["disabled"] == 1   # m1+core+episodic 建,m2 停用
    items = await worldbook_store.list_entries(fake_redis)
    assert len(items) == 5   # 4 自动 + 1 manual
    assert any(e.id == "wb_keep" and e.source == "manual" for e in items)
    # 幂等:重跑结果一致(先删全部自动来源再建,不叠加)
    r2 = await worldbook_store.rebuild_auto(fake_redis, ["10001"])
    assert r2 == r1
    assert len(await worldbook_store.list_entries(fake_redis)) == 5


async def test_rebuild_dry_run_no_write(fake_redis):
    """dry-run 只统计不写库"""
    from memory import store as mem_store
    await mem_store.upsert_long_term(fake_redis, "10001", _mem("m1"))
    r = await worldbook_store.rebuild_auto(fake_redis, ["10001"], dry_run=True)
    assert r["created"] == 1 and r["disabled"] == 0
    assert await worldbook_store.list_entries(fake_redis) == []
