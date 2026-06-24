"""
代人聊天 B 实时接管测试（V1.1 M13）
service 层（fake_redis）：开关 / open_pending 单 active / resolve / clear
REST 层（client）：toggle / status / answer 410。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. V1.1 M13 覆盖 takeover service 核心 + rest_takeover 端点
"""
from core.config import settings
from takeover import service as ts

HEADERS = {"X-Access-Token": settings.access_token}


# —— service 层（fake_redis）——

async def test_toggle(fake_redis):
    assert await ts.is_takeover_enabled(fake_redis, "o1") is False
    await ts.set_takeover_enabled(fake_redis, "o1", True)
    assert await ts.is_takeover_enabled(fake_redis, "o1") is True
    await ts.set_takeover_enabled(fake_redis, "o1", False)
    assert await ts.is_takeover_enabled(fake_redis, "o1") is False


async def test_open_pending_incr_unique(fake_redis):
    p1 = await ts.open_takeover_request(fake_redis, "o1", "msg1")
    p2 = await ts.open_takeover_request(fake_redis, "o1", "msg2")
    assert p1 != p2                                 # INCR 全局序列唯一


async def test_open_pending_single_active(fake_redis):
    p1 = await ts.open_takeover_request(fake_redis, "o1", "msg1")
    p2 = await ts.open_takeover_request(fake_redis, "o1", "msg2")
    assert await ts.get_active_pending(fake_redis, "o1") == p2   # 后者覆盖（per-object 单 active）


async def test_resolve_success(fake_redis):
    pid = await ts.open_takeover_request(fake_redis, "o1", "你好")
    r = await ts.resolve_takeover_answer(fake_redis, "o1", pid, "嗨")
    assert r == {"user_text": "你好", "answer": "嗨"}


async def test_resolve_expired_pending(fake_redis):
    assert await ts.resolve_takeover_answer(fake_redis, "o1", "takeover_999", "x") is None


async def test_resolve_wrong_object(fake_redis):
    pid = await ts.open_takeover_request(fake_redis, "o1", "你好")
    assert await ts.resolve_takeover_answer(fake_redis, "o2", pid, "x") is None


async def test_resolve_superseded(fake_redis):
    """旧 pending 被新请求覆盖后不再可 resolve（非 active）"""
    p1 = await ts.open_takeover_request(fake_redis, "o1", "msg1")
    await ts.open_takeover_request(fake_redis, "o1", "msg2")   # 覆盖
    assert await ts.resolve_takeover_answer(fake_redis, "o1", p1, "x") is None


async def test_clear_pending(fake_redis):
    pid = await ts.open_takeover_request(fake_redis, "o1", "你好")
    await ts.clear_pending(fake_redis, "o1", pid)
    assert await ts.get_active_pending(fake_redis, "o1") is None


# —— REST 层（client）——

def test_takeover_toggle_and_status(client):
    r = client.post("/api/v1/takeover/toggle",
                    json={"object_id": "o1", "enabled": True}, headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    s = client.get("/api/v1/takeover/status", params={"object_id": "o1"}, headers=HEADERS).json()
    assert s["enabled"] is True


def test_takeover_answer_expired_returns_410(client):
    r = client.post("/api/v1/takeover/answer",
                    json={"object_id": "o1", "pending_id": "takeover_999", "answer": "x"},
                    headers=HEADERS)
    assert r.status_code == 410


def test_takeover_answer_missing_fields_400(client):
    r = client.post("/api/v1/takeover/answer",
                    json={"object_id": "o1"}, headers=HEADERS)
    assert r.status_code == 400


def test_takeover_toggle_missing_oid_400(client):
    r = client.post("/api/v1/takeover/toggle", json={"enabled": True}, headers=HEADERS)
    assert r.status_code == 400
