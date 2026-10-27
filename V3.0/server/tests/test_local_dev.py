"""
scripts/local_dev.py 冒烟测试(函数级 + HTTP 层)
覆盖三件事:redis 探测失败回退注入 fakeredis / 种子幂等门控 / TestClient 起 lifespan 后
health 与带 token 的 chat/sessions 均 200。import scripts.local_dev 本身是安全的
(模块级副作用仅 sys.path 调整,core/main 等重导入均在函数内,见被测文件头部说明)。
redis 注入说明:脚本注入与 conftest 的 fake_redis 注入的是同一模块属性 redis_client._redis,
本文件以 conftest 夹具为准,用例只测脚本函数与 HTTP 层,不与脚本注入互踩。

日期: 2026-10-25

2026-10-25
变更说明:
  1. 初版:3 用例——fakeredis 回退注入、种子幂等、lifespan+HTTP 冒烟(health/sessions)
"""
import asyncio

import fakeredis

import scripts.local_dev as local_dev
import storage.redis_client as redis_client
from core.config import settings


def test_setup_redis_fallback_to_fakeredis(monkeypatch):
    """探测失败路径:setup_redis 应回退注入 FakeAsyncRedis(decode_responses=True)并返回 FAKEREDIS"""
    monkeypatch.setattr(local_dev, "probe_redis", lambda: False)  # 模拟真库不可达(1-2s 内失败)
    mode = local_dev.setup_redis()
    try:
        assert mode == "FAKEREDIS"
        assert isinstance(redis_client._redis, fakeredis.FakeAsyncRedis)  # 注入到模块单例属性

        async def _roundtrip():
            # 行为级验证 decode_responses=True:写入 str 取回仍是 str(而非 bytes)
            await redis_client._redis.set("local_dev:test:k", "v")
            return await redis_client._redis.get("local_dev:test:k")

        assert asyncio.run(_roundtrip()) == "v"
    finally:
        redis_client._redis = None  # 复位单例,防注入泄漏到其它测试


async def test_seed_demo_data_idempotent(fake_redis):
    """种子幂等:首次写入;二次因 has_history 门控跳过,demo 的 block 数与消息数均不变"""
    from storage import chat_store
    assert await local_dev.seed_demo_data() is True     # 首次:真实写入(经 get_redis 即夹具注入的 fakeredis)
    blocks1 = len(await chat_store.list_blocks(fake_redis, "demo"))  # block 列表长度
    msgs1 = await chat_store.count_messages(fake_redis, "demo")      # 跨 block 消息总数
    assert blocks1 >= 1 and msgs1 >= 6                 # demo 会话 6 条消息(user/ai x2 轮 + proxy)
    assert await local_dev.seed_demo_data() is False   # 二次:幂等门控跳过(panel_dev 原版不幂等会翻倍)
    blocks2 = len(await chat_store.list_blocks(fake_redis, "demo"))
    msgs2 = await chat_store.count_messages(fake_redis, "demo")
    assert blocks1 == blocks2 and msgs1 == msgs2       # append_message 每次生成新 mid,门控保证不新增


def test_http_smoke_with_lifespan(fake_redis):
    """HTTP 层冒烟:TestClient 起 lifespan(真启动路径)后 /health 200 且无 NapCat 连入,
    带 X-Access-Token 的 /api/v1/chat/sessions 200 且返回全部种子会话"""
    from fastapi.testclient import TestClient
    from main import app
    # 先种数据(sessions 有内容可断言);asyncio.run 独立小事件环,读写的是夹具注入的 fakeredis
    asyncio.run(local_dev.seed_demo_data())
    # 测试侧隔离:既有 watch 用例(m_v3)会把模块级 onebot.watch._recheck(asyncio.Event)
    # 绑到它自己的事件环,lifespan 掉线监控在 TestClient 的独立环里 await 它会报
    # "bound to a different event loop"。换新 Event(首次 await 才惰性绑定当前环),不改业务代码。
    import onebot.watch as watch
    watch._recheck = asyncio.Event()
    with TestClient(app) as client:  # with 语句触发 lifespan(adapter/redis 预热/插件/后台循环)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["onebot_connected"] is False  # 本地无 NapCat 反向 WS 连入
        resp2 = client.get("/api/v1/chat/sessions", headers={"X-Access-Token": settings.access_token})
        assert resp2.status_code == 200
        oids = {s["object_id"] for s in resp2.json()}
        assert oids == {"demo", "demo2_alice", "demo3_bob"}  # 3 个种子会话齐活
        resp3 = client.get("/api/v1/chat/sessions")  # 不带 token 必须被 401 拒绝
        assert resp3.status_code == 401
