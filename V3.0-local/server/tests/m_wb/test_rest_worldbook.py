"""
rest_worldbook REST 单测:entries CRUD 全路径 + stats + rebuild。
覆盖:鉴权 401 / 空库 / 新建校验(content 必填、非法 mode/position/probability 400)/
列表过滤 / PUT 部分更新与 404 / DELETE 物理删 / stats 字段 / rebuild(种记忆后重建,
manual 条目保留)。httpx ASGITransport 直挂 router(照 test_rest_dream 模式)。

日期: 2026-10-26

2026-10-26
变更说明:
  1. 新增:世界书 REST 6 端点测试
"""
import httpx
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_worldbook import router as worldbook_router
from core.config import settings
from memory import worldbook_store
from memory.models import MemoryItem

_H = {"X-Access-Token": "t-token"}


def _wire(monkeypatch, fake):
    """搭独立 app + fakeredis(rest_worldbook 经 get_redis() 拿到 fake)"""
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(worldbook_router)
    return app


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


# ================ 鉴权 ================

async def test_requires_token(monkeypatch, fake_redis):
    """无 token:全部端点 401"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/worldbook/entries")).status_code == 401
        assert (await ac.post("/api/v1/worldbook/entries", json={})).status_code == 401
        assert (await ac.put("/api/v1/worldbook/entries/x", json={})).status_code == 401
        assert (await ac.delete("/api/v1/worldbook/entries/x")).status_code == 401
        assert (await ac.get("/api/v1/worldbook/stats")).status_code == 401
        assert (await ac.post("/api/v1/worldbook/rebuild", json={})).status_code == 401


# ================ entries CRUD ================

async def test_create_and_list_and_filter(monkeypatch, fake_redis):
    """新建(source=manual)→ 列表倒序 → source/enabled 过滤"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/worldbook/entries", headers=_H, json={
            "title": "她怕打雷", "content": "打雷的时候她会缩起来。",
            "keys": ["打雷", "雷声"], "mode": "trigger", "position": "before_memories",
        })
        assert r.status_code == 200
        e = r.json()
        assert e["source"] == "manual" and e["keys"] == ["打雷", "雷声"]
        assert e["enabled"] is True and e["token_estimate"] > 0
        # 第二条停用条目
        r2 = await ac.post("/api/v1/worldbook/entries", headers=_H,
                           json={"content": "常驻设定", "mode": "always"})
        assert r2.status_code == 200
        eid2 = r2.json()["id"]
        await ac.put(f"/api/v1/worldbook/entries/{eid2}", headers=_H, json={"enabled": False})
        # 列表:2 条;过滤 source=manual 2 条;enabled=false 1 条
        items = (await ac.get("/api/v1/worldbook/entries", headers=_H)).json()["items"]
        assert len(items) == 2
        only_off = (await ac.get("/api/v1/worldbook/entries",
                                 headers=_H, params={"enabled": "false"})).json()["items"]
        assert len(only_off) == 1 and only_off[0]["id"] == eid2
        bad = (await ac.get("/api/v1/worldbook/entries",
                            headers=_H, params={"source": "alien"}))
        assert bad.status_code == 400


async def test_create_validation(monkeypatch, fake_redis):
    """新建校验:content 必填 400 / 非法 mode/position 回退默认(不 400,容错)"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/worldbook/entries", headers=_H,
                          json={"title": "无内容"})
        assert r.status_code == 400
        r2 = await ac.post("/api/v1/worldbook/entries", headers=_H,
                           json={"content": "内容", "mode": "weird", "position": "nowhere"})
        assert r2.status_code == 200
        assert r2.json()["mode"] == "trigger"
        assert r2.json()["position"] == "before_memories"


async def test_update_entry(monkeypatch, fake_redis):
    """PUT 部分更新:改 title/keys/enabled;probability 越界 400;空 patch 400;404"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        eid = (await ac.post("/api/v1/worldbook/entries", headers=_H,
                             json={"content": "原内容"})).json()["id"]
        r = await ac.put(f"/api/v1/worldbook/entries/{eid}", headers=_H,
                         json={"title": "新标题", "keys": ["打雷"], "enabled": False})
        assert r.status_code == 200
        j = r.json()
        assert j["title"] == "新标题" and j["keys"] == ["打雷"] and j["enabled"] is False
        assert j["content"] == "原内容"            # 未出现在 patch 保留
        assert (await ac.put(f"/api/v1/worldbook/entries/{eid}", headers=_H,
                             json={"probability": 2.0})).status_code == 400
        assert (await ac.put(f"/api/v1/worldbook/entries/{eid}", headers=_H,
                             json={})).status_code == 400
        assert (await ac.put("/api/v1/worldbook/entries/wb_none", headers=_H,
                             json={"title": "x"})).status_code == 404


async def test_delete_entry(monkeypatch, fake_redis):
    """DELETE 物理删;重复删 404"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        eid = (await ac.post("/api/v1/worldbook/entries", headers=_H,
                             json={"content": "删我"})).json()["id"]
        assert (await ac.delete(f"/api/v1/worldbook/entries/{eid}",
                                headers=_H)).json() == {"deleted": True}
        assert (await ac.delete(f"/api/v1/worldbook/entries/{eid}",
                                headers=_H)).status_code == 404


# ================ stats / rebuild ================

async def test_stats(monkeypatch, fake_redis):
    """stats:总数/启用/常驻/来源分布/注入统计"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        await ac.post("/api/v1/worldbook/entries", headers=_H,
                      json={"content": "常驻", "mode": "always"})
        await ac.post("/api/v1/worldbook/entries", headers=_H, json={"content": "触发"})
        await worldbook_store.record_injection(fake_redis, ["wb_x"], tokens=30)
        s = (await ac.get("/api/v1/worldbook/stats", headers=_H)).json()
        assert s["total"] == 2 and s["enabled"] == 2 and s["always"] == 1
        assert s["by_source"] == {"manual": 2}
        assert s["today_injections"] == 1 and s["avg_tokens"] == 30.0


async def test_rebuild(monkeypatch, fake_redis):
    """rebuild:种长期记忆+core → 重建出自动条目;manual 保留;指定 oid 只扫该对象"""
    from memory import store as mem_store
    app = _wire(monkeypatch, fake_redis)
    await mem_store.upsert_long_term(fake_redis, "10001", MemoryItem(
        id="mem_1", content="他喜欢猫", category="preference"))
    await mem_store.set_core(fake_redis, "10002", [])
    async with await _ac(app) as ac:
        await ac.post("/api/v1/worldbook/entries", headers=_H, json={"content": "手写"})
        r = (await ac.post("/api/v1/worldbook/rebuild", headers=_H,
                           json={"object_id": "10001"})).json()
        assert r["created"] == 1 and r["oids"] == ["10001"]
        items = (await ac.get("/api/v1/worldbook/entries", headers=_H)).json()["items"]
        assert len(items) == 2
        assert {e["source"] for e in items} == {"manual", "memory"}
        # 幂等:重跑不叠加
        r2 = (await ac.post("/api/v1/worldbook/rebuild", headers=_H,
                            json={"object_id": "10001"})).json()
        assert r2 == r
        items2 = (await ac.get("/api/v1/worldbook/entries", headers=_H)).json()["items"]
        assert len(items2) == 2


async def test_rebuild_all_objects(monkeypatch, fake_redis):
    """rebuild 缺省 object_id:扫全部对象(list_objects)"""
    from memory import store as mem_store
    app = _wire(monkeypatch, fake_redis)
    for oid in ("10001", "10002"):
        await mem_store.upsert_long_term(fake_redis, oid, MemoryItem(
            id=f"mem_{oid}", content=f"{oid}的记忆", category="fact"))
    async with await _ac(app) as ac:
        r = (await ac.post("/api/v1/worldbook/rebuild", headers=_H, json={})).json()
        assert sorted(r["oids"]) == ["10001", "10002"]
        assert r["created"] == 2


async def test_create_put_type_validation(monkeypatch, fake_redis):
    """审查修复:数值字段坏类型 → 400(原版裸 int()/float() 抛 ValueError 会 500);
    enabled 传字符串 → 400(原版 store 层 bool("false")=True 语义正好反转)"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        # create 侧:order/cooldown_minutes/probability 坏类型
        assert (await ac.post("/api/v1/worldbook/entries", headers=_H,
                              json={"content": "x", "order": "abc"})).status_code == 400
        assert (await ac.post("/api/v1/worldbook/entries", headers=_H,
                              json={"content": "x", "cooldown_minutes": "later"})).status_code == 400
        assert (await ac.post("/api/v1/worldbook/entries", headers=_H,
                              json={"content": "x", "probability": "high"})).status_code == 400
        # put 侧:order 坏类型 / enabled 传字符串
        eid = (await ac.post("/api/v1/worldbook/entries", headers=_H,
                             json={"content": "原"})).json()["id"]
        assert (await ac.put(f"/api/v1/worldbook/entries/{eid}", headers=_H,
                             json={"order": "abc"})).status_code == 400
        assert (await ac.put(f"/api/v1/worldbook/entries/{eid}", headers=_H,
                             json={"enabled": "false"})).status_code == 400


async def test_put_source_not_editable(monkeypatch, fake_redis):
    """审查修复:source/source_ref 移出可编辑白名单——PUT 带上须被静默忽略
    (改脏值会破坏 by_ref 幂等索引产生重复条目;改成自动来源还会被 rebuild 物理删)"""
    app = _wire(monkeypatch, fake_redis)
    async with await _ac(app) as ac:
        eid = (await ac.post("/api/v1/worldbook/entries", headers=_H,
                             json={"content": "手写设定"})).json()["id"]
        r = await ac.put(f"/api/v1/worldbook/entries/{eid}", headers=_H,
                         json={"title": "改名", "source": "memory", "source_ref": "10001:mX"})
        assert r.status_code == 200
        j = r.json()
        assert j["title"] == "改名"
        assert j["source"] == "manual" and j["source_ref"] == ""
