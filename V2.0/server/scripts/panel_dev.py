"""
M7 面板本地验收启动器(本地开发/演示用工具,不入镜像仅本地跑)
用 fakeredis 注入 + 种子示例数据(默认人设/mood 5 档/对话/score 正负样本/mood 历史)
+ 静态托管 dashboard/dist,uvicorn 单端口 :8000 跑通前后端(同源),便于本地验收。
无 Redis/Docker/.env 时用此脚本单端口跑通面板;凭证均为假值,不发真请求。
启动:cd V2.0/server && mychat/python.exe scripts/panel_dev.py
访问:http://localhost:8000   登录 token:dev-token   示例 object_id:demo

作者: 李文煜
日期: 2026-06-30

2026-07-02
变更说明：
  1. 入库(原"不入库"措辞修正):与 real_*_check.py 同为开发工具,一致入库,便于他人本地验收面板
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# 同级导入:把 server/app 加入 sys.path(与 conftest 一致)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
# 假 QQ 凭证(避免无 secret 时 init_client 派生失败;不发真请求)+ 面板 token
os.environ.setdefault("APPID", "1000000000")
os.environ.setdefault("QQ_APP_SECRET", "panel-dev-secret-1234567890abcdef")
os.environ.setdefault("ACCESS_TOKEN", "dev-token")

import fakeredis
import storage.redis_client as redis_client
# 注入 fakeredis(内存,无需真 Redis/Docker),lifespan 与请求共用同一实例
redis_client._redis = fakeredis.FakeAsyncRedis(decode_responses=True)


async def _seed():
    """种子示例数据,让面板各页验收有内容可看"""
    from storage.redis_client import get_redis
    from persona.store import init_default_if_absent
    from mood.service import seed_default_kinds, set_mood
    from storage import chat_store
    from score import service as score_service
    r = await get_redis()
    await init_default_if_absent(r)          # 默认人设(Persona 页)
    await seed_default_kinds(r)              # mood 默认 5 档(Mood 档位管理)
    oid = "demo"
    # 示例对话(同一 block,History 页)
    await chat_store.append_message(r, oid, sender="user", content="你好呀,今天过得怎么样?")
    mid_good = await chat_store.append_message(r, oid, sender="ai", content="嘿嘿,今天心情很不错呢 ◍˃ᵕ˂◍ 想你啦~")
    await chat_store.set_score(r, mid_good, score_base=88, mood_value=0.8, mood_bias=2)
    await chat_store.append_message(r, oid, sender="user", content="随便敷衍一下就行")
    mid_bad = await chat_store.append_message(r, oid, sender="ai", content="哦。")
    await chat_store.set_score(r, mid_bad, score_base=38, mood_value=0.3, mood_bias=-1)
    # 正负样本(Score 页正反样例)
    await score_service.record_negative_sample(r, oid, mid_bad, "哦。", 37)
    await r.lpush(f"mychat:score:pos:{oid}", json.dumps(
        {"mid": mid_good, "text": "嘿嘿,今天心情很不错呢 ◍˃ᵕ˂◍ 想你啦~",
         "score": 90, "ts": int(time.time() * 1000)}, ensure_ascii=False))
    # mood 历史曲线(Mood 实时监控页)
    for m in (0.35, 0.5, 0.55, 0.7, 0.8, 0.75):
        await set_mood(r, oid, m)
    print("[panel_dev] 种子完成: object_id=demo(2 轮对话 正88/负37 + 正负样本 + mood 历史 6 点)")


asyncio.run(_seed())

import uvicorn
from main import app
print("[panel_dev] 启动 http://127.0.0.1:8000 (fakeredis + 静态托管 dist,同源)")
print("[panel_dev] 登录 token=dev-token,示例 object_id=demo")
uvicorn.run(app, host="127.0.0.1", port=8000)
