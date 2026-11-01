"""
NapCat 掉线监控单测(2026-09-15):
两级探测状态机(WS 连接态 + WebUI QQ 登录态)+ Redis 状态镜像 + REST 端点。
核心场景 = "WS 活着但 QQ 离线"(09-08~15 事故形态,只有主动探测能发现)。

日期: 2026-09-15

2026-11-01
变更说明:
  1. 新增 WS 断线自愈配套测试:触发时机(first_delay 后)/login 形态不插手/未配脚本不触发/
     退避间隔/上限升级告警/恢复在线重置计数(fixture 同步重置 _heal)
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
    """每测重置 watch 内存单例(模块级状态,防跨测泄漏;含自愈计数 2026-11-01)"""
    import onebot.watch as watch
    watch._status.update({"state": "unknown", "detail": "", "ws_ok": False,
                          "login_ok": None, "last_check_ts": 0, "offline_since_ts": 0})
    watch._reset_heal()
    yield
    watch._status.update({"state": "unknown", "detail": "", "ws_ok": False,
                          "login_ok": None, "last_check_ts": 0, "offline_since_ts": 0})
    watch._reset_heal()


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


# ================ WS 断线自愈(2026-11-01,大肥鱼 5 天静默断线事故配套) ================

def _set_offline(ws_ok=False, offline_sec=600):
    """把 watch 拨到「WS 断线已持续 offline_sec 秒」的状态(check_once 依据 offline_since_ts 决策)"""
    import time
    import onebot.watch as watch
    now = int(time.time())
    watch._status.update({"state": "offline", "detail": "反向WS未连接", "ws_ok": ws_ok,
                          "login_ok": None, "last_check_ts": now,
                          "offline_since_ts": now - offline_sec})


def _heal_on(monkeypatch, script="heal.ps1"):
    """打开自愈配置(WebUI 探测关闭,聚焦 WS 口径;first_delay=300/retry=600)"""
    monkeypatch.setattr(settings, "napcat_heal_enable", True)
    monkeypatch.setattr(settings, "napcat_heal_script", script)
    monkeypatch.setattr(settings, "napcat_heal_first_delay_sec", 300)
    monkeypatch.setattr(settings, "napcat_heal_retry_interval_sec", 600)
    monkeypatch.setattr(settings, "napcat_webui_base", "")
    monkeypatch.setattr(settings, "napcat_webui_token", "")


async def test_heal_triggers_after_delay(fake_redis, monkeypatch):
    """WS 断线超 first_delay 且脚本已配 → 触发自愈并计数(本轮状态仍 offline,重连下轮确认)"""
    import onebot.watch as watch
    from onebot import ws_client
    _heal_on(monkeypatch)
    monkeypatch.setattr(ws_client, "is_connected", lambda: False)
    _set_offline()
    calls = []
    monkeypatch.setattr(watch, "_sync_heal", lambda script, timeout=300: calls.append(script) or 0)
    st = await watch.check_once(fake_redis)
    assert len(calls) == 1 and calls[0] == "heal.ps1"
    assert watch._heal["attempts"] == 1
    assert st["state"] == "offline"


async def test_heal_waits_first_delay(fake_redis, monkeypatch):
    """断线刚发生 2s(< first_delay) → 不触发(给 NapCat 自身重连留窗口)"""
    import onebot.watch as watch
    from onebot import ws_client
    _heal_on(monkeypatch)
    monkeypatch.setattr(ws_client, "is_connected", lambda: False)
    _set_offline(offline_sec=2)
    calls = []
    monkeypatch.setattr(watch, "_sync_heal", lambda script, timeout=300: calls.append(script) or 0)
    await watch.check_once(fake_redis)
    assert calls == []


async def test_heal_skipped_for_login_form(fake_redis, monkeypatch):
    """QQ 登录态失效形态(ws 在 login=False) → 自愈不插手(须扫码,重启无意义)"""
    import onebot.watch as watch
    from onebot import ws_client
    _heal_on(monkeypatch)
    monkeypatch.setattr(settings, "napcat_webui_base", "http://127.0.0.1:6080")
    monkeypatch.setattr(settings, "napcat_webui_token", "tok")
    monkeypatch.setattr(ws_client, "is_connected", lambda: True)
    monkeypatch.setattr(watch, "_sync_probe_login", lambda b, t: False)
    _set_offline(ws_ok=True)
    calls = []
    monkeypatch.setattr(watch, "_sync_heal", lambda script, timeout=300: calls.append(script) or 0)
    st = await watch.check_once(fake_redis)
    assert calls == []
    assert st["ws_ok"] is True and st["login_ok"] is False


async def test_heal_disabled_without_script(fake_redis, monkeypatch):
    """脚本未配置(默认空) → 自愈不启用,行为同旧版纯告警"""
    import onebot.watch as watch
    from onebot import ws_client
    monkeypatch.setattr(settings, "napcat_heal_enable", True)
    monkeypatch.setattr(settings, "napcat_heal_script", "")   # 默认空=禁用
    monkeypatch.setattr(ws_client, "is_connected", lambda: False)
    _set_offline()
    calls = []
    monkeypatch.setattr(watch, "_sync_heal", lambda script, timeout=300: calls.append(script) or 0)
    await watch.check_once(fake_redis)
    assert calls == []


async def test_heal_retry_backoff(fake_redis, monkeypatch):
    """相邻两次自愈需间隔 retry_interval:首轮触发后立即再测 → 不重复触发"""
    import onebot.watch as watch
    from onebot import ws_client
    _heal_on(monkeypatch)
    monkeypatch.setattr(ws_client, "is_connected", lambda: False)
    _set_offline()
    calls = []
    monkeypatch.setattr(watch, "_sync_heal", lambda script, timeout=300: calls.append(script) or 0)
    await watch.check_once(fake_redis)
    assert len(calls) == 1
    await watch.check_once(fake_redis)          # 刚试过,退避中
    assert len(calls) == 1
    assert watch._heal["attempts"] == 1


async def test_heal_max_attempts_then_alert(fake_redis, monkeypatch):
    """attempts 到上限 → 不再触发,alerted 置位(升级告警只发一次)"""
    import onebot.watch as watch
    from onebot import ws_client
    _heal_on(monkeypatch)
    monkeypatch.setattr(ws_client, "is_connected", lambda: False)
    _set_offline()
    watch._heal.update({"attempts": 3, "last_ts": 0, "alerted": False})
    calls = []
    monkeypatch.setattr(watch, "_sync_heal", lambda script, timeout=300: calls.append(script) or 0)
    await watch.check_once(fake_redis)
    assert calls == []
    assert watch._heal["alerted"] is True
    await watch.check_once(fake_redis)          # 已告警过,不重复
    assert watch._heal["alerted"] is True


async def test_heal_reset_on_recover(fake_redis, monkeypatch):
    """恢复 online → 自愈计数清零(下一个离线周期重新计满额;仅「从离线恢复」才重置)"""
    import time
    import onebot.watch as watch
    from onebot import ws_client
    _heal_on(monkeypatch)
    monkeypatch.setattr(ws_client, "is_connected", lambda: True)
    watch._heal.update({"attempts": 2, "last_ts": 1, "alerted": False})
    watch._status["offline_since_ts"] = int(time.time()) - 600   # 先处于离线周期
    st = await watch.check_once(fake_redis)
    assert st["state"] == "online"
    assert watch._heal["attempts"] == 0 and watch._heal["alerted"] is False


# ================ 登录态探测解读(2026-11-01 清浔误报实证) ================

def test_interpret_login_status():
    """CheckLoginStatus 解读:isLogin=True 在线;自动快速登录形态(状态机 offline 但
    loginError 含「已登录」)是在线不误报;真离线(loginError 空/待扫码)返 False"""
    from onebot.watch import _interpret_login_status as itp
    assert itp({"isLogin": True, "loginError": ""}) is True
    assert itp({"isLogin": False, "loginPhase": "offline", "coreReady": False,
                "loginError": "当前账号(1145077465)已登录,无法重复登录"}) is True
    assert itp({"isLogin": False, "loginPhase": "offline", "loginError": ""}) is False
    assert itp({"isLogin": False}) is False
    assert itp({}) is False
