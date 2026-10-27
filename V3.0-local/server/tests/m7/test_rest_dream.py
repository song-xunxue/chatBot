"""
rest_diary REST 单测(dream 插件配套):日记查看 2 端点 + 手动补跑 1 端点。
覆盖:鉴权 401 / 空库 list / list 字段与倒序(元素恰为 {date,tone,excerpt},excerpt=diary 前 60 字)/
detail(缓存命中、缓存删后文件兜底、404、格式非法与非真实日期 400)/
run(成功 200 原样返回 entry+参数透传、None→503、date 非法与未来 400、
object_id 缺省取最近会话/显式透传)。run_dream 全部打桩不真调 LLM;DIARY_DIR 指 tmp_path。

日期: 2026-10-26

2026-10-26
变更说明：
  1. 新增 rest_diary 3 端点测试(鉴权/列表/详情/手动跑)
"""
import json
from datetime import date, datetime

import httpx
from fastapi import FastAPI

import plugins.dream.service as dream_service
import plugins.dream.storage as dream_storage
import storage.redis_client as redis_client
from api.rest_diary import router as diary_router
from core.config import settings
from storage import chat_store

_H = {"X-Access-Token": "t-token"}


def _entry(d: str, diary: str = "今天他突然夸我记性好,有点开心。", tone: str = "positive") -> dict:
    """构造一条最小完整 entry(save_entry 只要求 date 合法)"""
    return {"date": d, "dream": "梦见发光的海", "diary": diary, "mood_curve": [],
            "key_events": ["被夸"], "dream_tone": tone, "object_id": "10001",
            "created_ts": 1798000000000}


def _wire(monkeypatch, fake, tmp_path):
    """搭独立 app + fakeredis + 日记目录指 tmp_path(rest_diary 经 get_redis() 拿到 fake)"""
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    monkeypatch.setattr(dream_storage, "DIARY_DIR", tmp_path)
    app = FastAPI()
    app.include_router(diary_router)
    return app, fake


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


# ================ 鉴权 / list ================

async def test_requires_token(monkeypatch, fake_redis, tmp_path):
    """无 token:三个端点一律 401"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/diary/list")).status_code == 401
        assert (await ac.get("/api/v1/diary/2026-10-25")).status_code == 401
        assert (await ac.post("/api/v1/diary/run", json={})).status_code == 401


async def test_list_empty(monkeypatch, fake_redis, tmp_path):
    """空库 → items 空列表"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/diary/list", headers=_H)
        assert r.status_code == 200
        assert r.json() == {"items": []}


async def test_list_fields_and_order(monkeypatch, fake_redis, tmp_path):
    """倒序 + 元素恰为 {date,tone,excerpt};excerpt=diary 前 60 字(超长加省略号)"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    await dream_storage.save_entry(fake, _entry("2026-10-24"), keep_days=90)
    await dream_storage.save_entry(fake, _entry("2026-10-25", diary="今" * 80), keep_days=90)
    async with await _ac(app) as ac:
        items = (await ac.get("/api/v1/diary/list", headers=_H)).json()["items"]
    assert items == [
        {"date": "2026-10-25", "tone": "positive", "excerpt": "今" * 60 + "…"},
        {"date": "2026-10-24", "tone": "positive", "excerpt": "今天他突然夸我记性好,有点开心。"},
    ]


# ================ detail ================

async def test_detail_hit_404_and_bad_date(monkeypatch, fake_redis, tmp_path):
    """命中(缓存路径)→200 全量;删缓存仍 200(文件兜底);查无 404;格式非法/非真实日期 400"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    entry = _entry("2026-10-25")
    await dream_storage.save_entry(fake, entry, keep_days=90)
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/diary/2026-10-25", headers=_H)
        assert r.status_code == 200 and r.json() == entry
        await fake.delete("mychat:diary:2026-10-25")   # 清缓存,逼走文件路径
        r2 = await ac.get("/api/v1/diary/2026-10-25", headers=_H)
        assert r2.status_code == 200 and r2.json()["date"] == "2026-10-25"
        assert (await ac.get("/api/v1/diary/2026-01-01", headers=_H)).status_code == 404
        assert (await ac.get("/api/v1/diary/20261025", headers=_H)).status_code == 400
        assert (await ac.get("/api/v1/diary/2026-02-30", headers=_H)).status_code == 400


# ================ run(手动补跑) ================

async def test_run_success_returns_entry(monkeypatch, fake_redis, tmp_path):
    """成功:200 原样返回 entry;oid 显式透传;date 解析为 date 对象;params 回退 DEFAULT_PARAMS"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    seen = []

    async def fake_run_dream(redis, oid, target, params):
        seen.append((redis is fake, oid, target, params))
        return _entry("2026-10-25")

    monkeypatch.setattr(dream_service, "run_dream", fake_run_dream)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/diary/run", headers=_H,
                          json={"date": "2026-10-25", "object_id": "88888"})
        assert r.status_code == 200
        assert r.json() == _entry("2026-10-25")
    assert seen == [(True, "88888", date(2026, 10, 25), dict(dream_service.DEFAULT_PARAMS))]
    # date 缺省 = 今天(不传 body.date)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/diary/run", headers=_H,
                              json={"object_id": "88888"})).status_code == 200
    assert seen[-1][2] == dream_service._now().date()


async def test_run_none_returns_503(monkeypatch, fake_redis, tmp_path):
    """run_dream 返 None(无素材/LLM 不可用)→ 503"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)

    async def fake_run_dream(redis, oid, target, params):
        return None

    monkeypatch.setattr(dream_service, "run_dream", fake_run_dream)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/diary/run", headers=_H,
                          json={"date": "2026-10-25", "object_id": "1"})
        assert r.status_code == 503


async def test_run_bad_and_future_date_400(monkeypatch, fake_redis, tmp_path):
    """date 非法/非真实日期/未来(固定 _now=2026-10-26)→ 400,且不触达 run_dream"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    monkeypatch.setattr(dream_service, "_now", lambda: datetime(2026, 10, 26, 12))
    seen = []

    async def fake_run_dream(redis, oid, target, params):
        seen.append(target)
        return _entry("2026-10-25")

    monkeypatch.setattr(dream_service, "run_dream", fake_run_dream)
    async with await _ac(app) as ac:
        for bad in ("not-a-date", "2026-02-30", "2026-12-31"):
            r = await ac.post("/api/v1/diary/run", headers=_H,
                              json={"date": bad, "object_id": "1"})
            assert r.status_code == 400, bad
    assert seen == []


async def test_run_object_id_fallback_and_explicit(monkeypatch, fake_redis, tmp_path):
    """object_id 缺省:无任何会话 → 400;有最近会话 → 取其 oid;显式传入优先透传"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    seen = []

    async def fake_run_dream(redis, oid, target, params):
        seen.append(oid)
        return _entry("2026-10-25")

    monkeypatch.setattr(dream_service, "run_dream", fake_run_dream)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/diary/run", headers=_H, json={})).status_code == 400
        await chat_store.append_message(fake, "10001", sender="user", content="在吗")
        assert (await ac.post("/api/v1/diary/run", headers=_H, json={})).status_code == 200
        assert (await ac.post("/api/v1/diary/run", headers=_H,
                              json={"object_id": "77777"})).status_code == 200
    assert seen == ["10001", "77777"]
