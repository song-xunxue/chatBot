"""
本地端到端验证脚本（B 方案）
在本地无 Redis/Docker 的 Windows 环境下，用 fakeredis 替代 Redis，启动真实 FastAPI server，
再用 WebSocket 客户端发 user_msg，验证真实 GLM 流式回复的端到端链路：
  client → /ws(token 鉴权) → run_stream(取历史/人设/流式调 GLM/存历史) → ai_start/ai_chunk×N/ai_done

运行：python e2e_check.py（用 mychat conda 环境）

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M2 验证：本地端到端流式验证脚本（fakeredis + 真实 GLM）
"""
import asyncio
import json
import sys
from pathlib import Path

# sys.path：server/app（main/core/storage/llm/pipeline）+ 项目根（shared）
_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE / "app"), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fakeredis  # 纯 Python 内存 Redis，替代真实 Redis
import storage.redis_client as redis_client  # 注入点：把 _redis 单例替换为 fakeredis
from main import app  # FastAPI 应用实例
from core.config import settings  # 读取 .env（access_token / glm_api_key）
from shared.protocol import TYPE_AI_START, TYPE_AI_DONE  # 出站事件类型（断言用）

PORT = 8011  # 本地验证端口，避开 8000（云端）防冲突


async def run_client():
    """WS 客户端：连 /ws、发 user_msg、收 ai_start/ai_chunk×N/ai_done 流式回复"""
    import websockets  # 异步 WebSocket 客户端
    from shared.protocol import (
        TYPE_USER_MSG, TYPE_AI_START, TYPE_AI_CHUNK, TYPE_AI_DONE, TYPE_ERROR, envelope,
    )

    url = f"ws://127.0.0.1:{PORT}/ws?token={settings.access_token}"
    print(f"[client] 连接 ws://127.0.0.1:{PORT}/ws?token=***")

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps(envelope(
            TYPE_USER_MSG,
            {"text": "你好，请用一句话介绍你自己"},
            object_id="e2e",
        )))
        seq, chunks, full, err = [], [], "", None
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)  # GLM 流式首字可能数秒
            msg = json.loads(raw)
            t = msg["type"]
            seq.append(t)
            if t == TYPE_AI_CHUNK:
                chunks.append(msg["payload"]["delta"]["text"])
            elif t == TYPE_AI_DONE:
                full = msg["payload"]["text"]
                break
            elif t == TYPE_ERROR:
                err = msg["payload"].get("message", "")
                break
        return seq, chunks, full, err


async def main() -> bool:
    # 1.注入 fakeredis（本地无 Redis/Docker）
    redis_client._redis = fakeredis.FakeAsyncRedis()
    print("[setup] 已注入 fakeredis（本地无 Redis）")

    # 2.同 event loop 内启动 uvicorn，保证 fakeredis 不跨 loop
    from uvicorn import Config, Server
    server = Server(Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    serve_task = asyncio.create_task(server.serve())
    await asyncio.sleep(2.0)  # 等 server 启动
    print(f"[server] uvicorn 已在 127.0.0.1:{PORT} 启动")

    ok = False
    try:
        seq, chunks, full, err = await run_client()
        print("\n===== 端到端结果 =====")
        print("消息类型序列:", " -> ".join(seq))
        if err:
            print("FAIL: 收到 error:", err)
        else:
            joined = "".join(chunks)
            print(f"ai_chunk 分片数: {len(chunks)}")
            print(f"流式拼接: {joined}")
            print(f"ai_done 完整回复: {full}")
            # 链路正确性断言
            assert seq[0] == TYPE_AI_START, "首条应为 ai_start"
            assert seq[-1] == TYPE_AI_DONE, "末条应为 ai_done"
            assert len(chunks) >= 1, "至少应有 1 个分片"
            assert full, "ai_done 文本不应为空"
            assert joined == full, "分片拼接应等于 ai_done 完整回复"
            print("\nPASS: 端到端流式验证通过")
            ok = True
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=5)
        except asyncio.TimeoutError:
            pass
    return ok


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
