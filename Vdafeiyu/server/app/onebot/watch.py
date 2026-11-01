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

2026-11-01 断线自愈:大肥鱼 10-27 17:52 WS 断线静默 5 天的教训——QQ 进程活着但 NapCat WS
客户端死亡,外部看护门控误判"待扫码"不动作,期间所有私聊零上报。补主动治愈:_maybe_heal
按断线时长决策(仅 WS 断线形态;QQ 登录态失效须扫码不归它管),退避重试跑 heal-napcat.ps1
(优雅关 QQ→绝不强杀守登录态→幂等启动器拉起→快速登录重连),单周期上限 max_attempts,
超过升级 ERROR 等人工;恢复在线自动重置计数。脚本路径/阈值全配置化(.env 可关)。

日期: 2026-09-15

2026-11-01
变更说明：
  1. 新增 WS 断线自愈:_sync_heal(to_thread 无窗跑脚本)+_maybe_heal(时长决策/退避/上限/
     升级告警),check_once 集成;恢复在线重置计数
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

# 自愈状态(2026-11-01):当前离线周期的尝试计数/上次尝试时刻/是否已升级告警。
# 恢复在线时整体重置(offline_since_ts 变 0 即视为新周期)。
_heal: dict = {"attempts": 0, "last_ts": 0, "alerted": False}


def _reset_heal() -> None:
    """恢复在线/新离线周期:重置自愈计数(告警标记一并清,下个周期重新计)"""
    _heal.update({"attempts": 0, "last_ts": 0, "alerted": False})


def _sync_heal(script: str, timeout: int = 300) -> int:
    """同步执行自愈脚本(to_thread 里跑):powershell 无窗(CREATE_NO_WINDOW)跑 heal-napcat.ps1。
    返回退出码:0=脚本完成(Wait-SvcHealth 已确认 onebot_connected)/2=QQ 优雅关闭失败(不强杀)/
    3=启动器失败/其他=异常。-1=超时或执行失败。"""
    import subprocess
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
            capture_output=True, timeout=timeout,
            creationflags=0x08000000)   # CREATE_NO_WINDOW:子控制台从创建起不可见(silent_run 同款)
        return proc.returncode
    except subprocess.TimeoutExpired:
        logger.error("自愈脚本超时(%ss,可能卡在等登录),放弃本轮", timeout)
        return -1
    except Exception as e:
        logger.error("自愈脚本执行失败: %s", e)
        return -1


async def _maybe_heal() -> None:
    """WS 断线自愈决策(check_once 判定 offline 且 ws_ok=False 后调用):
    - 不碰「QQ 登录态失效」形态(login_ok=False):那须扫码,重启救不了,自愈只会白折腾
    - 断线持续 >= first_delay 才动手(NapCat 自身有重连,先给它留窗口)
    - 相邻尝试间隔 >= retry_interval(退避防打桩);单周期上限 max_attempts
    - 超上限升级 ERROR 一次(面板横幅已有红幅常驻);恢复在线由 check_once 重置计数"""
    if not (settings.napcat_heal_enable and settings.napcat_heal_script):
        return
    now = int(time.time())
    if _heal["attempts"] >= settings.napcat_heal_max_attempts:
        if not _heal["alerted"]:
            _heal["alerted"] = True
            logger.error("NapCat 自愈已尝试 %d 次仍未恢复,停止自动治愈,请人工跑启动器"
                         "(脚本=%s)", _heal["attempts"], settings.napcat_heal_script)
        return
    offline_dur = now - _status["offline_since_ts"]
    if offline_dur < settings.napcat_heal_first_delay_sec:
        return
    if _heal["last_ts"] and now - _heal["last_ts"] < settings.napcat_heal_retry_interval_sec:
        return
    _heal["attempts"] += 1
    _heal["last_ts"] = now
    logger.warning("NapCat WS 断线已 %ds,触发第 %d/%d 次自愈:优雅重启 NapCat 链",
                   offline_dur, _heal["attempts"], settings.napcat_heal_max_attempts)
    rc = await asyncio.to_thread(_sync_heal, settings.napcat_heal_script)
    if rc == 0:
        logger.info("自愈脚本完成(rc=0),立即复检确认 WS 重连")
        request_recheck()           # 不等满 interval,马上验证治愈效果
    elif rc == 2:
        logger.warning("自愈中止:QQ 优雅关闭失败(按铁律不强杀守登录态),稍后重试或需人工")
    else:
        logger.warning("自愈脚本未成功 rc=%s,按退避间隔重试", rc)


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


def _interpret_login_status(data: dict) -> bool:
    """解读 CheckLoginStatus 的 data → 实际是否在线(纯函数便于单测)。
    2026-11-01 清浔实证坑:QQNT 自动快速登录后 NapCat 状态机停在 offline(isLogin=False/
    coreReady=False),但 loginError 明说「已登录,无法重复登录」——实际在线,按误报修正;
    真离线(待扫码)时 loginError 为空,返回 False 不放水。"""
    if bool(data.get("isLogin")):
        return True
    return "已登录" in str(data.get("loginError", "") or "")


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
            return _interpret_login_status(data)
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
            _reset_heal()               # 新离线周期开始(计数清零重新计)
    else:
        if _status["offline_since_ts"]:
            _reset_heal()               # 恢复在线:自愈计数清零
        _status["offline_since_ts"] = 0

    # 2026-11-01 自愈接线:仅「WS 断线」形态主动治愈(QQ 登录态失效须扫码,重启无意义)
    if state == "offline" and not ws_ok:
        try:
            await _maybe_heal()
        except Exception:
            logger.exception("自愈决策异常(不影响监控主流程)")

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
