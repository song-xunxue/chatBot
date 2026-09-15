"""
NapCat 掉线监控(2026-09-15,09-08~15 QQ 登录态失效静默丢 8 天数据的教训)

两级信号,覆盖两种掉线形态:
  ① 反向WS连接态(onebot.ws_client.is_connected):断 = NapCat 容器停/重启/网络断,
    入出站全断,服务端可自知;
  ② QQ 登录态(NapCat WebUI /api/QQLogin/CheckLoginStatus 探测):**WS 活着但 QQ 离线**
    = 本次事故形态——隧道在、绑定在,但腾讯侧登录态失效,消息静默不到服务器,最隐蔽,
    只有主动探测能发现。

状态流:check_once → 内存单例 + Redis hash mychat:system:napcat_status(state/detail/
ws_ok/login_ok/last_check_ts/offline_since_ts) → REST GET /system/napcat-status →
面板(MainLayout/MobileLayout)60s 轮询,offline 时红色横幅常驻"消息正在丢失"。

探测实现:WebUI 鉴权 POST /api/auth/login {"hash": sha256(token+".napcat")} 取 Credential
→ Bearer 调 CheckLoginStatus 读 data.isLogin。经同步 httpx.Client + asyncio.to_thread
(沿用 TTS 的 frp 兼容经验;WebUI 在宿主机 host-gateway,普通 HTTP 本无碍,统一保守)。

循环容错:探测异常记 unknown(不误报 offline),循环体全捕获——监控自身永远不能把主服务拖死。

作者: 李文煜
日期: 2026-09-15
"""
import asyncio
import hashlib
import logging
import time

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# Redis 状态键(REST 侧跨请求读取;重启后首轮探测前 REST 可读旧值)
STATUS_KEY = "mychat:system:napcat_status"

# 内存状态(探测循环写入;REST 直接读,免 Redis 往返)
_status: dict = {"state": "unknown", "detail": "", "ws_ok": False,
                 "login_ok": None, "last_check_ts": 0, "offline_since_ts": 0}

# 立即复检信号(WS 连接/断开时 ws_client 调 request_recheck 唤醒循环——消除服务重启后
# 最长一个 interval 的过期状态:重启 → 首轮探测 offline → WS 重连成功但状态要等 5min 才翻绿)
_recheck: asyncio.Event = asyncio.Event()


def request_recheck() -> None:
    """请求立即复检(ws_client 绑定/断开时调;幂等,循环侧消费后 clear)"""
    _recheck.set()


def get_status() -> dict:
    """当前监控状态(REST /system/napcat-status 数据源)"""
    return dict(_status)


def json_str(v) -> str:
    """状态值统一字符串化(Redis hash 字段;bool→1/0,None→空串)"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def _sync_probe_login(base: str, token: str) -> bool | None:
    """同步探测 QQ 登录态(WebUI CheckLoginStatus;to_thread 里跑)。
    返 True/False;任何异常返 None(unknown,不误报)。"""
    try:
        with httpx.Client(timeout=5.0) as c:
            h = hashlib.sha256((token + ".napcat").encode()).hexdigest()
            r = c.post(f"{base}/api/auth/login", json={"hash": h})
            r.raise_for_status()
            cred = (r.json().get("data") or {}).get("Credential", "")
            if not cred:
                return None
            r2 = c.post(f"{base}/api/QQLogin/CheckLoginStatus",
                        headers={"Authorization": f"Bearer {cred}"})
            r2.raise_for_status()
            data = r2.json().get("data") or {}
            return bool(data.get("isLogin"))
    except Exception as e:
        logger.warning("NapCat WebUI 登录态探测失败(unknown 不误报): %s", e)
        return None


async def check_once(redis) -> dict:
    """执行一次两级探测,更新内存 + Redis 状态并记录状态迁移日志。返回状态 dict。"""
    from onebot import ws_client

    ws_ok = ws_client.is_connected()
    login_ok: bool | None = None
    if settings.napcat_webui_base and settings.napcat_webui_token:
        login_ok = await asyncio.to_thread(
            _sync_probe_login, settings.napcat_webui_base, settings.napcat_webui_token)

    prev = _status["state"]
    if not ws_ok:
        state, detail = "offline", "反向WS未连接(NapCat 容器停/重启或网络断,入出站全断)"
    elif login_ok is False:
        state, detail = "offline", "QQ 登录态失效(WS 在但消息不到,须 WebUI 扫码重登)"
    elif login_ok is None:
        state, detail = ("online" if ws_ok else "offline"), \
                        "反向WS已连接(QQ 登录态未探测:NAPCAT_WEBUI_TOKEN 未配置)"
    else:
        state, detail = "online", "反向WS已连接 + QQ 登录在线"

    now = int(time.time())
    _status.update({"state": state, "detail": detail, "ws_ok": ws_ok,
                    "login_ok": login_ok, "last_check_ts": now})
    if state == "offline":
        if not _status["offline_since_ts"]:
            _status["offline_since_ts"] = now
    else:
        _status["offline_since_ts"] = 0

    # 状态迁移日志(off 持续刷 WARNING 提醒,转 online 一次性 INFO)
    if state == "offline":
        logger.warning("NapCat 掉线告警: %s(自 %s 起,消息未在记录!)",
                       detail, time.strftime("%m-%d %H:%M", time.localtime(_status["offline_since_ts"])))
    elif prev == "offline":
        logger.info("NapCat 已恢复在线: %s", detail)

    try:
        await redis.hset(STATUS_KEY, mapping={k: json_str(v) for k, v in _status.items()})
    except Exception:
        logger.exception("NapCat 状态写 Redis 失败(不影响内存状态)")
    return dict(_status)


async def _watch_loop(redis) -> None:
    """周期探测循环(lifespan 启动;体全捕获,监控自身异常绝不中断主服务)。
    睡眠可被 request_recheck 提前唤醒(WS 连接/断开即时刷新,不等满 interval)。"""
    while True:
        try:
            await check_once(redis)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("NapCat 监控轮次异常(继续下一轮)")
        _recheck.clear()
        try:
            await asyncio.wait_for(_recheck.wait(), timeout=settings.napcat_watch_interval_sec)
        except asyncio.TimeoutError:
            pass


def start_watch_loop(redis) -> asyncio.Task:
    """启动监控循环(立即首轮探测 + 周期轮询),返回任务(lifespan 收纳,关闭时 cancel)"""
    return asyncio.create_task(_watch_loop(redis))
