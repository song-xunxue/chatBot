"""
NapCat 掉线监控单测(2026-09-15):
两级探测状态机(WS 连接态 + WebUI QQ 登录态)+ Redis 状态镜像 + REST 端点。
核心场景 = "WS 活着但 QQ 离线"(09-08~15 事故形态,只有主动探测能发现)。

作者: 李文煜
日期: 2026-09-15
"""
import httpx
import pytest
from fastapi import FastAPI

import storage.redis_client as redis_client
from api.rest_system import router as system_router
from core.config import settings

_H = {"X-Access-Token": "t-token"}


@pytest.fixture(autouse=True)
def _reset_watch_state():
    """每测重置 watch 内存单例(模块级状态,防跨测泄漏)"""
    import onebot.watch as watch
    watch._status.update({"state": "unknown", "detail": "", "ws_ok": False,
                          "login_ok": None, "last_check_ts": 0, "offline_since_ts": 0})
    yield
    watch._status.update({"state": "unknown", "detail": "", "ws_ok": False,
                          "login_ok": None, "last_check_ts": 0, "offline_since_ts": 0})


@pytest.fixture
def _webui_on(monkeypatch):
    """启用 WebUI 探测(探测函数由各测自行 mock)"""
    monkeypatch.setattr(settings, "napcat_webui_base", "http://127.0.0.1:6080")
    monkeypatch.setattr(settings, "napcat_webui_token", "tok")


async def test_watch_ws_down(fake_redis, monkeypatch, _webui_on):
    """WS 断 → offline(入出站全断形态)"""
    import onebot.watch as watch
    from onebot import ws_client
    monkeypatch.setattr(ws_client, "is_connected", lambda: False)
    st = await watch.check_once(fake_redis)
    assert st["state"] == "offline" and st["ws_ok"] is False
    assert "反向WS" in st["detail"]


async def test_watch_ws_up_qq_offline(fake_redis, monkeypatch, _webui_on):
    """WS 在 + QQ 登录态失效 → offline(09-08~15 事故形态,最隐蔽)"""
    import onebot.watch as watch
    from onebot import ws_client
    monkeypatch.setattr(ws_client, "is_connected", lambda: True)
    monkeypatch.setattr(watch, "_sync_probe_login", lambda b, t: False)
    st = await watch.check_once(fake_redis)
    assert st["state"] == "offline"
    assert st["ws_ok"] is True and st["login_ok"] is False
    assert "QQ 登录态失效" in st["detail"]


async def test_watch_all_online(fake_redis, monkeypatch, _webui_on):
    """WS 在 + QQ 在线 → online;状态镜像写 Redis"""
    import onebot.watch as watch
    from onebot import ws_client
    monkeypatch.setattr(ws_client, "is_connected", lambda: True)
    monkeypatch.setattr(watch, "_sync_probe_login", lambda b, t: True)
    st = await watch.check_once(fake_redis)
    assert st["state"] == "online"
    assert st["login_ok"] is True
    # Redis 镜像(hash 字段全字符串)
    mirror = await fake_redis.hgetall(watch.STATUS_KEY)
    assert mirror["state"] == "online" and mirror["ws_ok"] == "1" and mirror["login_ok"] == "1"


async def test_watch_probe_fail_no_false_alarm(fake_redis, monkeypatch, _webui_on):
    """WebUI 探测异常返 None → 不误报 offline(WS 口径 online)"""
    import onebot.watch as watch
    from onebot import ws_client
    monkeypatch.setattr(ws_client, "is_connected", lambda: True)
    monkeypatch.setattr(watch, "_sync_probe_login", lambda b, t: None)
    st = await watch.check_once(fake_redis)
    assert st["state"] == "online" and st["login_ok"] is None


async def test_watch_no_webui_config(fake_redis, monkeypatch):
    """WebUI 未配置 → 仅 WS 口径(不调探测,token 空跳过)"""
    import onebot.watch as watch
    from onebot import ws_client
    monkeypatch.setattr(settings, "napcat_webui_base", "")
    monkeypatch.setattr(settings, "napcat_webui_token", "")
    monkeypatch.setattr(ws_client, "is_connected", lambda: True)
    called = []
    monkeypatch.setattr(watch, "_sync_probe_login", lambda b, t: called.append(1))
    st = await watch.check_once(fake_redis)
    assert st["state"] == "online" and not called


async def test_watch_recheck_wakes_loop(monkeypatch, fake_redis):
    """request_recheck 唤醒循环:WS 绑定/断开后立即复检,不等满 interval"""
    import asyncio
    import onebot.watch as watch
    monkeypatch.setattr(settings, "napcat_watch_interval_sec", 600)   # 长 interval,靠唤醒
    calls = []

    async def _fake_check(redis):
        calls.append(1)
        # 首轮后模拟 WS 恢复的状态
        watch._status.update({"state": "online", "detail": "ok", "ws_ok": True,
                              "login_ok": True, "last_check_ts": 1, "offline_since_ts": 0})

    monkeypatch.setattr(watch, "check_once", _fake_check)
    task = asyncio.create_task(watch._watch_loop(fake_redis))
    await asyncio.sleep(0.05)
    assert len(calls) == 1                       # 首轮立即探测
    watch.request_recheck()                      # WS 变化信号
    await asyncio.sleep(0.05)
    assert len(calls) == 2                       # 被唤醒复检,未等 600s
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_napcat_status_endpoint(monkeypatch, fake_redis):
    """REST GET /system/napcat-status:鉴权 + 返回内存单例字段"""
    import onebot.watch as watch
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    monkeypatch.setattr(settings, "access_token", "t-token")
    watch._status.update({"state": "offline", "detail": "QQ 登录态失效",
                          "ws_ok": True, "login_ok": False,
                          "last_check_ts": 123, "offline_since_ts": 100})
    app = FastAPI()
    app.include_router(system_router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        assert (await ac.get("/api/v1/system/napcat-status")).status_code == 401   # 未带 token
        r = await ac.get("/api/v1/system/napcat-status", headers=_H)
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "offline" and body["login_ok"] is False
        assert body["offline_since_ts"] == 100
