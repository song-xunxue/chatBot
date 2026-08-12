"""
M-V3-0 最小验证:OneBot v11 反向 WebSocket echo 服务(websockets 17 API)。

用途:验证「标准 QQ 用户身份(经 NapCat)收发私聊消息」通道是否稳定 + 评估封号风控。
不接 V2.0 pipeline,纯 echo(收到什么原样回发),只测通道与风控,不测业务。

工作方式:
  1. WebSocket 服务端监听 8091/ws(NapCat 配反向WS指向本机此端口)。
  2. NapCat 登录小号后主动连上来,鉴权 access_token。
  3. 收到 OneBot 事件(post_type=message, message_type=private)→ 解析 raw_message →
     通过同一条反向 WS 发 OneBot Action(send_private_msg)原样回发。
  4. 全程带时间戳日志(收/发/掉线/重连),供 7 天风控观察。

回发机制(fire-and-forget):NapCat 反向WS模式不保证回 Action 响应包,
  故发完 action 即记「已提交」,不等响应(消息是否送达以 NapCat 执行/用户接收为准);
  若 NapCat 碰巧回了响应(status+echo),记一条 [响应] 日志作辅助。

启动(venv):
  cd ~/napcat-test/echo && ./venv/bin/python echo_test.py
  默认监听 0.0.0.0:8091,鉴权 token = "v3test-token"
  环境变量覆盖:WS_PORT / WS_PATH / WS_TOKEN / SELF_ID(小号QQ号,过滤自发消息)

作者: 李文煜
日期: 2026-08-12
"""
import os
import json
import asyncio
from datetime import datetime

from websockets.asyncio.server import serve, ServerConnection
from websockets.http11 import Response

# —— 配置(环境变量覆盖)——
WS_PORT = int(os.getenv("WS_PORT", "8091"))
WS_PATH = os.getenv("WS_PATH", "/ws")
WS_TOKEN = os.getenv("WS_TOKEN", "v3test-token")          # 反向WS鉴权(NapCat 配置一致)
SELF_ID = os.getenv("SELF_ID", "")                          # 小号QQ号,过滤自发消息(可选)

# —— 每日主动发送(验证主动消息能力 + 兼作风控自检)——
PROACTIVE_TARGET = int(os.getenv("PROACTIVE_TARGET", "2690468347"))   # 主动发给谁(主号)
PROACTIVE_HH = int(os.getenv("PROACTIVE_HH", "21"))                    # 每天几点发(24h,默认21点档)
PROACTIVE_MM = int(os.getenv("PROACTIVE_MM", "3"))                     # 分钟(避开整点,默认21:03)

# 全局:当前连上来的 NapCat 连接(反向WS只有一个客户端)
napcat_ws: ServerConnection | None = None
_echo_seq = 0


def log(msg: str) -> None:
    """带时间戳日志(Windows 兼容纯 ASCII)"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


async def send_private_msg(user_id: int, text: str) -> dict:
    """通过已建立的反向 WS 连接发 OneBot Action(发私聊文本)。fire-and-forget:
    发完即返,不等响应(NapCat 反向WS模式不保证回 Action 响应包,死等会误报超时)。
    消息是否真送达以 NapCat 执行 / 用户端接收为准。"""
    global _echo_seq
    if napcat_ws is None:
        raise RuntimeError("NapCat 未连接(反向WS未建立),无法回发")
    _echo_seq += 1
    await napcat_ws.send(json.dumps({
        "action": "send_private_msg",
        "params": {"user_id": user_id, "message": text},
        "echo": f"echo-{_echo_seq}",
    }))
    return {"status": "sent"}


async def proactive_daily() -> None:
    """每天固定时间(PROACTIVE_HH:PROACTIVE_MM)主动给主号发一条带时间戳的测试句。
    作用:① 验证主动消息能力(OneBot 不受官方机器人月配额限制)② 兼作风控自检
    (发送成功=通道正常;连续失败=可能掉线/被风控,需人工查看)。"""
    while True:
        now = datetime.now()
        # 算下一次目标时间(今天指定时刻;已过则明天)
        target = now.replace(hour=PROACTIVE_HH, minute=PROACTIVE_MM, second=0, microsecond=0)
        if target <= now:
            # 计算明天:手动加一天(datetime 不支持直接 + 跨日 replace,用 timestamp)
            import time as _t
            target = datetime.fromtimestamp(_t.mktime(target.timetuple()) + 86400)
        wait_s = (target - now).total_seconds()
        log(f"[主动] 下次主动发送: {target:%Y-%m-%d %H:%M}(等 {wait_s/3600:.1f}h)")
        await asyncio.sleep(wait_s)
        # 发送(带日期时间戳,便于对账)
        text = f"[定时自检 {datetime.now():%Y-%m-%d %H:%M}] echo alive,主动消息测试"
        try:
            await send_private_msg(PROACTIVE_TARGET, text)
            log(f"[主动] 已提交 -> {PROACTIVE_TARGET}: {text}")
        except Exception as e:
            log(f"[主动] 失败: {e}(可能 NapCat 掉线/被风控,请检查)")


async def handle_event(data: dict) -> None:
    """处理 OneBot 事件。只处理私聊消息,原样 echo 回去。"""
    if data.get("post_type") != "message":
        pt = data.get("post_type", "?")
        if pt == "meta_event":
            sub = data.get("meta_event_type", "")
            if sub == "lifecycle":
                log(f"[元事件] lifecycle(连接已建立), self_id={data.get('self_id')}")
            # heartbeat 频繁,不打日志
        else:
            log(f"[事件] {pt}: {data.get('notice_type') or data.get('request_type')}")
        return

    if data.get("message_type") != "private":
        return  # 只处理私聊(验证场景)

    sender = data.get("sender", {})
    user_id = data.get("user_id")
    raw = data.get("raw_message", "")
    msg_id = data.get("message_id")
    if SELF_ID and str(user_id) == str(SELF_ID):
        return  # 过滤自发消息

    nickname = sender.get("nickname", str(user_id))
    log(f"[收] {nickname}({user_id}) msg_id={msg_id}: {raw}")

    # echo:原样回发(fire-and-forget)
    try:
        await send_private_msg(user_id, raw)
        log(f"[发] echo -> {user_id}: 已提交 | 内容: {raw}")
    except Exception as e:
        log(f"[发] 失败: {e}")


async def handler(ws: ServerConnection) -> None:
    """反向 WS 连接处理:NapCat 主动连上来。"""
    global napcat_ws
    napcat_ws = ws
    log(f"[连接] NapCat 已连上: {ws.remote_address}")
    try:
        async for raw_msg in ws:
            try:
                data = json.loads(raw_msg)
            except json.JSONDecodeError:
                continue
            # ① 带 status+echo = 我方 Action 的响应(fire-and-forget,记录即丢弃)
            if "status" in data and "echo" in data:
                log(f"[响应] {data.get('echo')}: {data.get('status')} retcode={data.get('retcode')}")
                continue
            # ② 带 post_type = OneBot 事件
            if "post_type" in data:
                await handle_event(data)
    except Exception as e:
        log(f"[断开/异常] {type(e).__name__}: {e}")
    finally:
        if napcat_ws is ws:
            napcat_ws = None
        log(f"[断开] NapCat 连接关闭: {ws.remote_address}")


def process_request(connection: ServerConnection, request) -> Response | None:
    """websockets 17 鉴权钩子:在连接建立前校验 path + access_token。
    NapCat 反向WS连接形如 ws://host:8091/ws?access_token=xxx,或 ws://host:8091?access_token=xxx(path=/)。"""
    path_only = request.path.split("?")[0]
    if path_only not in ("/", WS_PATH):
        log(f"[鉴权] 拒绝:path 不匹配 {request.path}")
        return connection.respond(404, "not found\n")
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(request.path).query)
    token_q = (q.get("access_token") or [""])[0]
    token_h = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    token = token_q or token_h
    if WS_TOKEN and token != WS_TOKEN:
        log(f"[鉴权] 拒绝:token 不匹配")
        return connection.respond(401, "unauthorized\n")
    return None


async def main() -> None:
    log(f"=== M-V3-0 echo 服务启动 ===")
    log(f"监听: ws://0.0.0.0:{WS_PORT}{WS_PATH}")
    log(f"鉴权 token: {WS_TOKEN}")
    log(f"回发方式: 反向WS Action(fire-and-forget,不等响应)")
    log(f"SELF_ID(过滤自发): {SELF_ID or '(未设)'}")
    log(f"主动发送: 每天 {PROACTIVE_HH:02d}:{PROACTIVE_MM:02d} -> QQ {PROACTIVE_TARGET}")
    log(f"等待 NapCat 反向WS连接...")
    log(f"(NapCat WebUI 配反向WS: ws://<服务器IP>:{WS_PORT}{WS_PATH}?access_token={WS_TOKEN})")
    async with serve(handler, "0.0.0.0", WS_PORT, process_request=process_request):
        # 并行:每日主动发送定时器(兼风控自检)
        asyncio.create_task(proactive_daily())
        await asyncio.Future()  # 永久运行


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("已停止")
