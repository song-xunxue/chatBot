"""
迁移脚本 migrate_worldbook 单测:幂等(重跑结果一致)/dry-run 不写/数量对照
(long_term+core+episodic 全量转条目,遗忘态→disabled)。直接 import scripts.migrate_worldbook
(模块级副作用仅 sys.path 调整,照 test_local_dev 模式)。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新增:迁移脚本幂等/dry-run/对照测试
"""
import asyncio

import scripts.migrate_worldbook as mig
from memory import store as mem_store, worldbook_store
from memory.models import MemoryItem, CoreFact, EpisodicEntry


def _seed(fake):
    """种两对象:10001(2 活 1 遗忘 + core 1 + episodic 1),10002(1 活)"""

    async def _run():
        for mid, forgotten in (("m1", False), ("m2", False), ("m3", True)):
            await mem_store.upsert_long_term(fake, "10001", MemoryItem(
                id=mid, content=f"记忆{mid}", category="fact", forgotten=forgotten))
        await mem_store.set_core(fake, "10001", [CoreFact(key="k1", content="核心事实")])
        await mem_store.append_episodic(fake, "10001", EpisodicEntry(
            id="epi_1", summary="情景摘要", span_start_ts=0, span_end_ts=0))
        await mem_store.upsert_long_term(fake, "10002", MemoryItem(
            id="m4", content="记忆m4", category="preference"))

    asyncio.run(_run())


def test_migrate_dry_run_no_write(monkeypatch, fake_redis, capsys):
    """dry-run:只统计对照不写库(数量对得上:活 3 遗忘 1 + core 1 + episodic 1)"""
    monkeypatch.setattr(mig.sys, "argv", ["migrate_worldbook.py", "--dry-run"])
    _seed(fake_redis)
    rc = asyncio.run(mig.main())
    assert rc == 0
    assert len(asyncio.run(worldbook_store.list_entries(fake_redis))) == 0   # 未写
    out = capsys.readouterr().out
    assert "long_term=4" in out and "core=1" in out and "episodic=1" in out
    assert "预计" in out


def test_migrate_creates_and_idempotent(monkeypatch, fake_redis, capsys):
    """实迁移:条目数 = 5 新建/启用 + 1 停用;重跑结果一致(幂等)"""
    monkeypatch.setattr(mig.sys, "argv", ["migrate_worldbook.py"])
    _seed(fake_redis)
    rc = asyncio.run(mig.main())
    assert rc == 0
    items = asyncio.run(worldbook_store.list_entries(fake_redis))
    assert len(items) == 6
    assert sum(1 for e in items if not e.enabled) == 1        # 遗忘 m3 → disabled
    assert {e.source for e in items} == {"memory", "summary"}
    out = capsys.readouterr().out
    assert "新建/启用 5" in out and "停用(遗忘态) 1" in out
    # 幂等:重跑条目数不变
    asyncio.run(mig.main())
    items2 = asyncio.run(worldbook_store.list_entries(fake_redis))
    assert len(items2) == 6


def test_migrate_single_oid(monkeypatch, fake_redis):
    """--oid 只迁移指定对象"""
    monkeypatch.setattr(mig.sys, "argv", ["migrate_worldbook.py", "--oid", "10002"])
    _seed(fake_redis)
    asyncio.run(mig.main())
    items = asyncio.run(worldbook_store.list_entries(fake_redis))
    assert len(items) == 1
    assert items[0].source_ref == "10002:m4"


def test_migrate_single_oid_keeps_other_objects(monkeypatch, fake_redis):
    """审查修复回归:先全量迁移(两对象条目都建好),再 --oid 10002 单对象重建——
    10001 的 5 条自动条目(core/episodic 含在内)必须保留;旧版 delete_all_auto
    无条件全局清场会把它们静默删光且不重建"""
    _seed(fake_redis)
    monkeypatch.setattr(mig.sys, "argv", ["migrate_worldbook.py"])
    asyncio.run(mig.main())                      # 全量:10001 5 条 + 10002 1 条 = 6
    monkeypatch.setattr(mig.sys, "argv", ["migrate_worldbook.py", "--oid", "10002"])
    asyncio.run(mig.main())                      # 单对象重建
    items = asyncio.run(worldbook_store.list_entries(fake_redis))
    assert len(items) == 6                       # 10001 全保留 + 10002 换新 1 条
    refs = [e.source_ref for e in items]
    assert "10002:m4" in refs
    assert "core:10001:k1" in refs               # core/episodic 的归属解析也正确
    assert "epi:10001:epi_1" in refs
