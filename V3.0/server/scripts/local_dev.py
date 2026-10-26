"""
V3.0 本地开发启动器(单进程一体跑前后端,本机免 Docker/真实 Redis)
流程:探测 settings.redis_url 指向的 Redis(同步 1s 超时 ping) -> 可达用真库不注入任何东西;
不可达打印 [WARN] 并注入 fakeredis.FakeAsyncRedis 到 storage.redis_client._redis(与 tests/conftest.py 同手法)。
种子示例数据照抄 scripts/panel_dev.py(3 会话 + 评分正负样本 + mood 历史),加幂等门控:
demo 会话已有历史(has_history)则整段跳过,真 redis 模式重复启动数据不翻倍;
默认人设与 mood 5 档由 lifespan 自带(init_default_if_absent + seed_default_kinds,幂等),不重做。
静态托管复用 main.py 的 dist catch-all(面板与 API 同源同端口,手机访问面板不受 CORS 影响);
局域网其它页面直调 REST 需在 .env 配 CORS_ORIGINS(默认只放行 localhost:5173)。
启动: C:/Users/26904/anaconda3/envs/mychat/python.exe V3.0/server/scripts/local_dev.py [--port 8091]

作者: 李文煜
日期: 2026-10-25

2026-10-25
变更说明:
  1. 初版:redis 探测回退 fakeredis + 幂等种子 + dist 缺失提示 + 局域网地址/token 来源打印
  2. REAL/WARN 两分支打印统一走 _mask_url 打码(REDIS_URL 内嵌密码防终端泄漏)
"""
import argparse
import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path

# server/app 加入 sys.path(与 tests/conftest.py 一致,使 core/storage/main 可同级导入;幂等防重复插入)
_APP_DIR = str(Path(__file__).resolve().parent.parent / "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

# 模块 import 安全:模块级副作用仅上面这一处 sys.path 调整;core.config/storage/main 等重导入
# 全部延后到函数内。原因有二:
# 1. --token 须在 core.config 实例化之前覆盖 os.environ(pydantic-settings 在 Settings()
#    实例化时读取 env 快照,之后再改环境变量对 settings.access_token 无效);
# 2. 测试文件 import scripts.local_dev 时不触发 uvicorn/种子等运行期副作用。


def _parse_args() -> argparse.Namespace:
    """解析命令行参数:端口默认 8091(V3.0 线上同款)/监听地址默认全网卡/跳过种子/覆盖面板 token"""
    parser = argparse.ArgumentParser(description="V3.0 local dev launcher (auto fakeredis fallback)")
    parser.add_argument("--port", type=int, default=8091, help="listen port (default 8091)")
    parser.add_argument("--host", default="0.0.0.0", help="listen host (default 0.0.0.0)")
    parser.add_argument("--no-seed", action="store_true", help="skip demo chat/score/mood seed")
    parser.add_argument("--token", default=None, help="override ACCESS_TOKEN before app config load")
    return parser.parse_args()


def probe_redis() -> bool:
    """同步探测 Redis 可达性:1s 连接/读写超时,失败快速返回 False(不长时间阻塞启动)"""
    import redis  # redis-py 同步客户端(仅探测用;业务运行仍走 storage/redis_client.py 异步单例)
    from core.config import settings
    url = settings.redis_url
    if settings.redis_password:
        # 与 storage/redis_client.py get_redis 同款密码注入:redis://host -> redis://:pwd@host
        url = url.replace("redis://", f"redis://:{settings.redis_password}@")
    try:
        # from_url 从 URL 建同步客户端;socket_connect_timeout/socket_timeout=1 保证 1-2s 内失败即回退
        client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()  # PING 探活:连不上/鉴权失败/超时都会抛异常
        client.close()
        return True
    except Exception:
        return False


def inject_fakeredis():
    """注入 fakeredis 到 redis_client._redis 单例(lifespan 与请求共用同一实例)。
    必须 FakeAsyncRedis + decode_responses=True:业务代码全部 await 且按 str 处理返回值。"""
    import fakeredis
    import storage.redis_client as redis_client
    redis_client._redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    return redis_client._redis


def _mask_url(url: str) -> str:
    """打印用打码:内嵌密码(redis://:pwd@host 或 redis://user:pwd@host)替换为 ***,防终端/日志泄漏;
    无密码的 redis://host:6390/0 不受影响(host:port 后无 @,正则不命中)"""
    import re
    return re.sub(r"(://[^@/]*:)[^@]+(@)", r"\1***\2", url)


def setup_redis() -> str:
    """探测并决定 redis 模式:可达返回 REAL(什么都不注入);不可达 [WARN] 后注入 fakeredis 返回 FAKEREDIS。
    必须在 uvicorn.run 之前完成:lifespan(main.py)首次 get_redis() 连不上会直接启动失败。"""
    from core.config import settings
    if probe_redis():
        print(f"[local_dev] redis mode: REAL ({_mask_url(settings.redis_url)})")
        return "REAL"
    print(f"[WARN] redis unreachable ({_mask_url(settings.redis_url)}) -> fallback to FAKEREDIS (in-memory, lost on exit)")
    inject_fakeredis()
    print("[local_dev] redis mode: FAKEREDIS")
    return "FAKEREDIS"


async def seed_demo_data() -> bool:
    """种子示例数据(照抄 scripts/panel_dev.py 的对话/评分/mood 部分,默认人设与 mood 5 档由 lifespan 自带)。
    幂等:demo 会话已有历史(has_history 为真)则跳过整段返回 False;真 redis 模式下重复启动数据不翻倍。"""
    from storage.redis_client import get_redis
    from storage import chat_store
    from score import service as score_service
    from mood.service import set_mood
    r = await get_redis()
    oid = "demo"
    if await chat_store.has_history(r, oid):  # 幂等门控:已有会话历史(存在 block 索引)则不重复种
        return False
    # 示例对话(demo,同一 block,2 轮 ai + 1 条代答 proxy,验证 ai/proxy 内联改分)
    await chat_store.append_message(r, oid, sender="user", content="你好呀,今天过得怎么样?")
    mid_good = await chat_store.append_message(r, oid, sender="ai", content="嘿嘿,今天心情很不错呢 ◍˃ᵕ˂◍ 想你啦~")
    await chat_store.set_score(r, mid_good, score_base=88, mood_value=0.8, mood_bias=2)
    await chat_store.append_message(r, oid, sender="user", content="随便敷衍一下就行")
    mid_bad = await chat_store.append_message(r, oid, sender="ai", content="哦。")
    await chat_store.set_score(r, mid_bad, score_base=38, mood_value=0.3, mood_bias=-1)
    # 代答消息(验证 proxy 改分;takeover 落盘 sender=proxy)
    await chat_store.append_message(r, oid, sender="user", content="帮我约下周末")
    mid_proxy = await chat_store.append_message(r, oid, sender="proxy", content="好呀,周末有空,咱们去吃那家新开的店吧~")
    await chat_store.set_score(r, mid_proxy, score_base=82, mood_value=0.7, mood_bias=1)
    # 第二会话(验证左侧会话列表多会话切换)
    oid2 = "demo2_alice"
    await chat_store.append_message(r, oid2, sender="user", content="在吗")
    mid2 = await chat_store.append_message(r, oid2, sender="ai", content="在的在的,怎么啦?")
    await chat_store.set_score(r, mid2, score_base=75, mood_value=0.6, mood_bias=1)
    # 第三会话(更旧,验证排序)
    oid3 = "demo3_bob"
    await chat_store.append_message(r, oid3, sender="user", content="晚安")
    await chat_store.append_message(r, oid3, sender="ai", content="晚安好梦~")
    # 正负样本(评分总览正反样例)
    await score_service.record_negative_sample(r, oid, mid_bad, "哦。", 37)
    await r.lpush(f"mychat:score:pos:{oid}", json.dumps(
        {"mid": mid_good, "text": "嘿嘿,今天心情很不错呢 ◍˃ᵕ˂◍ 想你啦~",
         "score": 90, "ts": int(time.time() * 1000)}, ensure_ascii=False))
    # mood 历史曲线(Mood 实时监控页,6 点)
    for m in (0.35, 0.5, 0.55, 0.7, 0.8, 0.75):
        await set_mood(r, oid, m)
    return True


def check_dist() -> bool:
    """检查前端构建产物 dashboard/dist/index.html;缺失仅提示不退出(API 照常,dev 也可 vite :5173 + proxy)。
    静态托管由 main.py 的 dist catch-all 提供,本脚本无需自行挂载。"""
    from core.config import PROJECT_ROOT
    index = PROJECT_ROOT / "dashboard" / "dist" / "index.html"
    if index.is_file():
        print(f"[local_dev] dist: OK ({index})")
        return True
    print("[WARN] dashboard/dist/index.html not found -> run 'npm run build' under V3.0/dashboard first")
    print("[local_dev] (API still served on this port; panel unavailable until dist built)")
    return False


def detect_lan_ip() -> str:
    """探测本机局域网 IP:UDP socket connect 8.8.8.8:80 让内核选默认路由(不真正发包,近零开销);
    失败退 gethostbyname(gethostname());再失败返回空串(由调用方提示用 ipconfig 查看)"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))  # UDP connect 只写路由不发包,选出默认网卡
        ip = sock.getsockname()[0]     # 本端地址即局域网出口 IP
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        sock.close()
    try:
        ip = socket.gethostbyname(socket.gethostname())  # 无外网路由时按主机名解析本机地址
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return ""


def token_info(cli_token: str | None) -> tuple[str, str]:
    """返回 (生效 ACCESS_TOKEN 值, 来源描述);优先级 --token > 环境变量 ACCESS_TOKEN > V3.0/.env > 代码默认值"""
    from core.config import settings, PROJECT_ROOT
    if cli_token:
        return cli_token, "--token (os.environ override)"
    env_val = os.environ.get("ACCESS_TOKEN")
    if env_val is not None:
        return env_val, "env ACCESS_TOKEN"
    env_file = PROJECT_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("ACCESS_TOKEN="):  # .env 显式配置了 token
                return settings.access_token, ".env (V3.0/.env)"
    return settings.access_token, "default (change-me-please)"


def main() -> None:
    """启动编排:token 覆盖 -> redis 探测/注入 -> 种子 -> dist 检查 -> 信息打印 -> uvicorn"""
    args = _parse_args()
    if args.token:
        # 必须发生在 import core.config 之前(本函数内后续的惰性导入才触发 Settings() 实例化)
        os.environ["ACCESS_TOKEN"] = args.token
    # 1. redis 探测/回退注入(在 uvicorn 之前:lifespan 首连失败会启动失败)
    mode = setup_redis()
    # 2. 种子(asyncio.run 独立事件环,在 uvicorn 事件环之前跑完;--no-seed 跳过)
    if args.no_seed:
        print("[local_dev] seed: skipped (--no-seed)")
    else:
        seeded = asyncio.run(seed_demo_data())
        print("[local_dev] seed: done (3 sessions + score pos/neg + mood x6)" if seeded
              else "[local_dev] seed: skipped (history exists, idempotent)")
    # 2b. 真 redis 分支:种子用的 asyncio.run 临时事件环已关闭,而 get_redis() 建的异步连接
    #     仍绑在那个环上,lifespan 复用它会在句柄收发时抛 "Event loop is closed"(实测启动失败)。
    #     丢弃单例,让 lifespan 在自己的事件环里重新建连;fakeredis 无 transport 不受影响,保持注入。
    if mode == "REAL":
        import storage.redis_client as _redis_client
        _redis_client._redis = None
    # 3. dist 检查(缺 dist 仅提示;API 照常)
    check_dist()
    # 4. token 与访问地址打印(面板与 API 同源同端口;手机连同一局域网直接开面板)
    tok, src = token_info(args.token)
    print(f"[local_dev] ACCESS_TOKEN = {tok}  (source: {src})")
    print("[local_dev] REST auth: header 'X-Access-Token: <token>' or query '?token=<token>'")
    ip = detect_lan_ip()
    if ip:
        print(f"[local_dev] LAN  : http://{ip}:{args.port}   (panel + API, same origin)")
    else:
        print(f"[WARN] LAN IP not detected; run 'ipconfig' to find it, then open http://<your-ip>:{args.port}")
    print(f"[local_dev] local: http://127.0.0.1:{args.port}")
    # 5. 启动(uvicorn.run 必须在 __main__ 入口链路内:模块被 import 时不执行到这里)
    import uvicorn
    from main import app
    print(f"[local_dev] starting uvicorn on {args.host}:{args.port} ...")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
