"""
OneBot v11 反向 WebSocket 入站(V3.0 M-V3-2,2026-08-16)
替代 V2.0 qq/webhook(官方机器人回调)与 M-V3-0 的独立 echo 脚本——同进程内完成收发。

链路:NapCat(登录真实 QQ 号)主动连本路由(/ws,query access_token 鉴权——契约与 M-V3-0 echo
一致,NapCat 端零改动无缝切换)→ 事件推送到本服务 → 处理:
  ① 私聊消息 → 代答拦截(takeover,同 webhook)/ 连发防抖合并(搬 webhook 逻辑)
     → 图片 vision(NapCat image segment url 免鉴权直接下载)→ MessageContext → pipeline
     → 经 adapter(ADAPTER=onebot 时即本模块 Action 通道)下发
  ② Action 响应(echo 匹配)→ 完成 call_action 的 future
  ③ 其余事件(meta/notice)忽略或记日志

出站通道 call_action:经当前 NapCat 连接发 OneBot Action,等响应(echo tag 匹配,超时软降级)。
adapter/onebot.py 的 send_text/send_voice 走这里。

self_id 过滤:仅处理 settings.onebot_self_id 的事件(接管对话的号;双号实验另一号连入时忽略)。

2026-09-07 手动回复感知(message_sent):NapCat 开 reportSelfMessage 后,管理员直接用角色 QQ 号
(手机端等)手动发的消息会以 post_type=message_sent 上报——服务器自己发的(经 call_action)按
响应 message_id 去重忽略;其余为手动回复 → takeover.record_manual_reply 落库+消化待答队列
(绝不重复下发)。修"手动回复不落聊天记录 + 待答队列堆积不消"两问题。

作者: 李文煜
日期: 2026-08-16

2026-09-07
变更说明：
  1. call_action 记录 send_private_msg 响应 message_id(_sent_msg_ids,1h 过期清理)+
     在途计数 _inflight_sends;新增 _handle_manual_sent/_extract_sent_content/
     _confirm_own_send(在途竞态:事件可能先于 Action 响应到达,短等再判)
  2. 对抗审查修复:① message_sent 改 create_task 异步分发(内联 await 会阻塞接收循环,
     等待期间 Action 响应帧无人处理,竞态等待必败)② _send_tags:_dispatch_response 同步记录
     send 响应 message_id(超时/迟到响应 future 已弃时也能记,防自发消息误判手动)
     ③ 竞态等待轮数覆盖 onebot_call_timeout ④ 陌生人门控(无会话/代答/待答的 oid 不记录)
     ⑤ 占位扩展(face/文件/转发/视频)+ string 格式 CQ 码识别 + 入队图片占位
  3. 线上实测修复:message_sent 接收方改从 target_id 解析(NapCat 的 user_id=senderUin=
     自己,接收方在 target_id=peerUin;原按 user_id 取致手动回复被陌生人门控误拦)
"""
import asyncio
import json
import logging
import time

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import settings
from pipeline.context import MessageContext
from pipeline.runner import run_stream

logger = logging.getLogger(__name__)

router = APIRouter(tags=["onebot-ws"])

# —— 出站通道状态:接管号的 NapCat 连接 + Action 响应 futures(echo tag -> Future)——
# 审查#3(多连接 last-wins 抢占防护):_ws 只绑定「接管号」(onebot_self_id)的连接——
# 其他号(如双号对照的旧号)连入只处理入站事件,绝不抢占出站通道。
_ws: WebSocket | None = None
_ws_self_id: str = ""        # 当前 _ws 绑定的 self_id(收首个带 self_id 事件时校验接管)
_pending: dict[str, asyncio.Future] = {}
_seq = 0

# —— 自己发送去重(2026-09-07 message_sent 链路)——
# NapCat 开 reportSelfMessage 后,服务器经 call_action 发的消息也会以 message_sent 上报;
# 记录响应 message_id 区分"服务器自己发的"(忽略,pipeline 已落库)vs"管理员手动发的"(记录)。
_sent_msg_ids: dict[str, float] = {}   # message_id -> 记录时刻(time.time,过期清理)
_send_tags: dict[str, float] = {}      # send_private_msg 的 echo tag -> 发出时刻(响应迟到/超时兜底)
_inflight_sends = 0                    # 在途 send_private_msg 数(message_sent 先于响应的竞态等待用)
_SENT_ID_TTL = 3600.0                  # 记录保留 1h(远大于事件上报延迟)
_SENT_RACE_ROUNDS = 8                  # 竞态等待轮数下限(实际取 max(本值, call_timeout/step),封顶 30)
_SENT_RACE_STEP = 0.25                 # 每轮等待秒数
_SENT_RACE_MAX_ROUNDS = 30             # 等待轮数封顶(30×0.25s=7.5s,防配置异常等过久)
# 纯媒体消息占位(入站代答入队/出站手动记录共用;文本优先,占位保上下文不丢消息)
_MEDIA_PLACEHOLDERS = {"record": "[语音]", "face": "[表情]", "mface": "[表情]",
                      "forward": "[转发]", "file": "[文件]", "video": "[视频]"}
# message_sent 异步分发任务强引用(防 GC 在完成前取消;完成后自动移除)
_EVENT_TASKS: set[asyncio.Task] = set()


def is_connected() -> bool:
    """NapCat 反向WS是否在线(adapter/takeover 判断出站可用)"""
    return _ws is not None


def _dispatch_response(data: dict) -> bool:
    """Action 响应分发:带 echo tag 的响应完成对应 future。返 True=已消费(是响应)。
    (websocket 主循环与单测共用)
    2026-09-07 审查修复:send_private_msg 的响应在此同步登记 message_id——不依赖
    call_action 协程恢复后才记(call_action 超时/迟到响应 future 已弃时也能记,
    防自发消息的 message_sent 迟到被误判为手动回复)。"""
    echo_tag = str(data.get("echo", "")) if isinstance(data, dict) else ""
    if echo_tag and ("status" in data or "retcode" in data):
        if echo_tag in _send_tags:
            _send_tags.pop(echo_tag, None)
            if str(data.get("retcode", 1)) == "0":
                d = data.get("data") or {}
                _note_sent_id(str(d.get("message_id", "") or ""))
        fut = _pending.get(echo_tag)
        if fut and not fut.done():
            fut.set_result(data)
        return True
    return False


def _note_sent_id(mid: str) -> None:
    """登记一个"自己发送"的 message_id(供 message_sent 去重);顺带清理过期记录(>1h)。"""
    if not mid or mid == "None":
        return
    now = time.time()
    for k in [k for k, t in _sent_msg_ids.items() if now - t > _SENT_ID_TTL]:
        _sent_msg_ids.pop(k, None)
    _sent_msg_ids[mid] = now


def _record_sent_msg_id(resp: dict) -> None:
    """从 Action 响应提取 message_id 并登记(call_action 正常路径)。"""
    data = resp.get("data") or {}
    _note_sent_id(str(data.get("message_id", "") or ""))


def _prune_send_tags() -> None:
    """清理过期 send echo tag 记录(>1h,同 _SENT_ID_TTL)。"""
    now = time.time()
    for k in [k for k, t in _send_tags.items() if now - t > _SENT_ID_TTL]:
        _send_tags.pop(k, None)


async def call_action(action: str, params: dict, timeout: float | None = None) -> dict | None:
    """经接管号连接发 OneBot Action,等响应(echo tag 匹配)。
    timeout 默认 settings.onebot_call_timeout(审查#4 接线,原先硬编码 5s);
    超时返 None(软降级,调用方按失败处理);未连接抛 RuntimeError。
    2026-09-07:send_private_msg 成功响应记录 message_id(message_sent 去重用)+
    在途计数(事件先于响应的竞态等待用)。"""
    global _seq, _inflight_sends
    if _ws is None:
        raise RuntimeError("NapCat 未连接(onebot 反向WS未建立)")
    if timeout is None:
        timeout = settings.onebot_call_timeout
    is_send = action == "send_private_msg"
    if is_send:
        _inflight_sends += 1
        _prune_send_tags()
    _seq += 1
    tag = f"act-{_seq}"
    if is_send:
        _send_tags[tag] = time.time()   # 响应分发兜底记录用(_dispatch_response 同步登记)
    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    _pending[tag] = fut
    try:
        await _ws.send_text(json.dumps({"action": action, "params": params, "echo": tag}))
        r = await asyncio.wait_for(fut, timeout)
        if is_send and r and r.get("status") == "ok":
            _record_sent_msg_id(r)
        return r
    except asyncio.TimeoutError:
        logger.warning("onebot action 响应超时 action=%s(NapCat 可能被风控拒发;若实发成功,"
                       "迟到响应经 _send_tags 兜底登记)", action)
        return None
    finally:
        if is_send:
            _inflight_sends -= 1
        _pending.pop(tag, None)


async def shutdown() -> None:
    """lifespan 关闭:断开 NapCat 连接"""
    global _ws
    if _ws is not None:
        try:
            await _ws.close()
        except Exception:
            pass
        _ws = None


def _on_event_task_done(task: asyncio.Task) -> None:
    """message_sent 异步分发任务完成回调:移出强引用集 + 记录未捕获异常。"""
    _EVENT_TASKS.discard(task)
    if not task.cancelled() and task.exception():
        logger.error("message_sent 处理任务异常", exc_info=task.exception())


@router.websocket("/ws")
async def onebot_ws(ws: WebSocket):
    """NapCat 反向WS入口。鉴权(审查#5 强化):query access_token(契约同 M-V3-0 echo)
    或 Authorization: Bearer <token> 头(OneBot 规范);ONEBOT_WS_TOKEN 未配置时拒绝连接
    (fail-closed——8091 公网可达,空 token 免鉴权不可接受)。
    多号场景:仅接管号(onebot_self_id)的连接绑定出站通道 _ws;其他号连入只处理入站(审查#3)。"""
    global _ws, _ws_self_id
    token_q = ws.query_params.get("access_token", "")
    token_h = (ws.headers.get("authorization") or "").replace("Bearer", "").strip()
    token = token_q or token_h
    if not settings.onebot_ws_token:
        logger.error("ONEBOT_WS_TOKEN 未配置,onebot WS 拒绝连接(fail-closed;公网端口不得裸奔)")
        await ws.close(code=4401)
        return
    if token != settings.onebot_ws_token:
        logger.warning("onebot WS 鉴权失败(token 不匹配),拒绝连接")
        await ws.close(code=4401)
        return
    await ws.accept()
    sid = None    # 本连接的 self_id(收首个带 self_id 事件时确定)
    logger.info("NapCat 反向WS已连接 client=%s", ws.client)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            # ① Action 响应(带 echo tag):完成对应 future
            if _dispatch_response(data):
                continue
            # ② 事件
            if isinstance(data, dict) and "post_type" in data:
                # 绑定时机=首个带 self_id 事件(此刻才知真假;接管号后到也能接管,
                # 修"首条连接暂绑+解绑后无人补位"的时序缺陷:非接管号先连会永久占空通道)
                s = str(data.get("self_id", "") or "")
                if s and sid is None:
                    sid = s
                    if not settings.onebot_self_id or sid == settings.onebot_self_id:
                        _ws, _ws_self_id = ws, sid      # 接管号绑定(覆盖任何当前占用)
                        logger.info("接管号 %s 绑定出站通道", sid)
                    else:
                        logger.info("连接 self_id=%s 非接管号(%s),仅收事件不绑定",
                                    sid, settings.onebot_self_id)
                try:
                    if data.get("post_type") == "message_sent":
                        # 审查修复(2026-09-07):message_sent 异步分发——自身发送判重需等待
                        # Action 响应落定,若内联 await 会阻塞接收循环,响应帧永远无人处理
                        # (_confirm_own_send 必然误判自己发的为手动)。create_task 让循环
                        # 继续消费响应帧。普通消息保持内联 await(保防抖合并的入队顺序)。
                        task = asyncio.create_task(_handle_event(data))
                        _EVENT_TASKS.add(task)               # 强引用防 GC 提前取消
                        task.add_done_callback(_on_event_task_done)
                    else:
                        await _handle_event(data)
                except Exception:
                    logger.exception("onebot 事件处理失败")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("onebot WS 连接异常")
    finally:
        if _ws is ws:
            _ws, _ws_self_id = None, ""
        logger.info("NapCat 反向WS断开 self_id=%s 出站占用=%s", sid, _ws is ws)


async def _handle_event(data: dict) -> None:
    """OneBot 事件分发:只处理接管号(self_id 过滤)的私聊消息,其余记日志忽略。
    2026-09-07:message_sent(自身发送上报,reportSelfMessage 开启后)单独分流。"""
    sid = str(data.get("self_id", ""))
    if settings.onebot_self_id and sid != settings.onebot_self_id:
        return   # 非接管号(双号场景另一号连入),忽略
    pt = data.get("post_type")
    if pt == "meta_event":
        if data.get("meta_event_type") == "lifecycle":
            logger.info("onebot lifecycle: 接管号 %s 已连接", sid)
        return
    if pt == "message_sent":
        if data.get("message_type") != "private":
            return   # 自己发的群聊消息,不在私聊代答场景
        await _handle_manual_sent(data)
        return
    if pt != "message" or data.get("message_type") != "private":
        return   # 只处理私聊(与 V2.0 webhook 场景一致)
    user_id = str(data.get("user_id", ""))
    if not user_id:
        return
    text, image_urls = _extract_content(data)
    msg_id = str(data.get("message_id", ""))
    sender = data.get("sender", {}) or {}
    logger.info("收到私聊(onebot) user=%s(%s) msg_id=%s 文本长度=%d 图片=%d",
                user_id, sender.get("nickname", ""), msg_id, len(text), len(image_urls))
    # 代答拦截(同 webhook:开启则入 takeover pending 队列,不进 pipeline)
    from storage import takeover_store
    from storage.redis_client import get_redis
    redis = await get_redis()
    if await takeover_store.is_enabled(redis, user_id):
        # 纯媒体消息(图片/语音/表情)占位入队(审查修复:原空文本入队,归档/合并时丢消息)
        qtext = _content_or_placeholder(data, text, image_urls)
        pid = await takeover_store.enqueue(redis, user_id,
                                           user_text=qtext, msg_id=msg_id)
        logger.info("代答模式入队(onebot) user=%s pid=%s", user_id, pid)
        return
    await _schedule_debounce(user_id, text, image_urls, msg_id)


async def _confirm_own_send(msg_id: str) -> bool:
    """判定 message_sent 是否服务器自己发送:命中 _sent_msg_ids 直 True;有在途 send 时
    短暂等待再判(message_sent 事件可能先于 Action 响应到达的竞态;审查修复:等待窗须
    覆盖 onebot_call_timeout,原固定 2s<默认 5s 存在窗口空洞),超窗仍无记录判 False。"""
    if msg_id and msg_id in _sent_msg_ids:
        return True
    rounds = max(_SENT_RACE_ROUNDS,
                 min(_SENT_RACE_MAX_ROUNDS,
                     int((settings.onebot_call_timeout + _SENT_RACE_STEP - 1) // _SENT_RACE_STEP)))
    for _ in range(rounds):
        if _inflight_sends <= 0:
            break
        await asyncio.sleep(_SENT_RACE_STEP)
        if msg_id and msg_id in _sent_msg_ids:
            return True
    return bool(msg_id) and msg_id in _sent_msg_ids


async def _handle_manual_sent(data: dict) -> None:
    """自身发送消息上报(NapCat reportSelfMessage 开启后 post_type=message_sent)。
    服务器自己发的(经 call_action,响应 message_id 命中去重集)→ 忽略(pipeline/takeover 已落库);
    其余 = 管理员手动用角色 QQ 号回复用户(手机端等)→ takeover.record_manual_reply
    (落库+消化待答队列,绝不重复下发)。"""
    msg_id = str(data.get("message_id", "") or "")
    if await _confirm_own_send(msg_id):
        logger.debug("message_sent 忽略(服务器自己发送) msg_id=%s", msg_id)
        return
    # 接收方解析(NapCat 实测坑,2026-09-07):message_sent 的 user_id=发送者(senderUin,
    # 即自己;initializeMessage 固定 user_id=senderUin),真正接收方在 target_id(peerUin)。
    # target_id 优先,缺失时兜底 user_id(兼容其它 OneBot 实现);解析到自己(无法定位接收方)跳过。
    oid = str(data.get("target_id", "") or "") or str(data.get("user_id", "") or "")
    if not oid or oid == str(data.get("self_id", "") or ""):
        logger.info("message_sent 无法定位接收方(target_id/user_id 均无效) self=%s 跳过",
                    data.get("self_id", ""))
        return
    content = _content_or_placeholder(data, *_extract_content(data))
    if not oid or not content:
        logger.info("message_sent 无法记录(缺接收方/无有效内容) user=%s 内容长度=%d",
                    oid, len(content))
        return
    # OneBot 事件 time 字段为秒,转毫秒;缺省用当前时刻
    try:
        sent_ts = int(float(data.get("time", 0) or 0) * 1000) or int(time.time() * 1000)
    except (TypeError, ValueError):
        sent_ts = int(time.time() * 1000)
    logger.info("手动回复(onebot message_sent) user=%s msg_id=%s 长度=%d",
                oid, msg_id, len(content))
    try:
        from storage import takeover_store, chat_store
        from storage.redis_client import get_redis
        redis = await get_redis()
        # 陌生人门控(审查修复):管理员用角色号私聊非用户对象时,不为陌生 oid 凭空建
        # 会话历史(防误触发面板 ensureOid 自动绑定);有代答开启/待答/已有会话才记录
        if not (await takeover_store.is_enabled(redis, oid)
                or await takeover_store.queue_length(redis, oid) > 0
                or await chat_store.has_history(redis, oid)):
            logger.info("message_sent 跳过(陌生对象:无会话/代答/待答) user=%s", oid)
            return
        from takeover import service as takeover_svc
        r = await takeover_svc.record_manual_reply(redis, oid, content, sent_ts=sent_ts)
        logger.info("手动回复已记录(onebot) user=%s 消化待答=%d 评分=%s",
                    oid, r.get("archived_pendings", 0), r.get("scored"))
    except Exception:
        logger.exception("手动回复记录失败(onebot) user=%s", oid)


def _content_or_placeholder(data: dict, text: str, image_urls: list[str]) -> str:
    """文本优先;纯媒体消息给占位(出站手动记录/入站代答入队共用,防空文本丢消息)。
    兼容 array(segment)与 string(CQ 码)两种上报格式。"""
    if text:
        return text
    if image_urls:
        return "[图片]"
    message = data.get("message")
    if isinstance(message, list):
        for seg in message:
            if isinstance(seg, dict):
                ph = _MEDIA_PLACEHOLDERS.get(str(seg.get("type", "")))
                if ph:
                    return ph
        return "[非文本消息]" if message else ""
    raw = message if isinstance(message, str) else str(data.get("raw_message", "") or "")
    for key, ph in _MEDIA_PLACEHOLDERS.items():
        if f"[CQ:{key}" in raw:
            return ph
    return ""


def _extract_content(data: dict) -> tuple[str, list[str]]:
    """提取消息文本与图片 url。兼容 array(segment 数组,NapCat messagePostFormat=array)
    与 string(CQ 码)两种上报格式。文本段拼接;image 段收 url。
    审查#6:所有 fallback 路径统一去 CQ 码(防残留码进 pipeline)。"""
    import re
    message = data.get("message")
    raw_message = str(data.get("raw_message", "") or "")

    def _strip_cq(s: str) -> str:
        return re.sub(r"\[CQ:[^\]]+\]", "", s).strip()

    texts: list[str] = []
    images: list[str] = []
    if isinstance(message, list):
        for seg in message:
            if not isinstance(seg, dict):
                continue
            stype = seg.get("type", "")
            sdata = seg.get("data", {}) or {}
            if stype == "text" and sdata.get("text"):
                texts.append(str(sdata["text"]))
            elif stype == "image":
                url = str(sdata.get("url", "") or "")
                if url:
                    images.append(url)
        # fallback:无 text/image 段时用 raw_message(去 CQ 码;图片 url 从 CQ 码抽)
        if not texts and not images and raw_message:
            for m in re.finditer(r"\[CQ:image,[^\]]*url=([^,\]]+)[^\]]*\]", raw_message):
                images.append(m.group(1))
            t = _strip_cq(raw_message)
            if t:
                texts.append(t)
        return "\n".join(texts).strip(), images
    # string 格式:raw_message 即 CQ 码文本;图片 url 正则抽 + 去码留纯文本
    text_part = raw_message
    for m in re.finditer(r"\[CQ:image,[^\]]*url=([^,\]]+)[^\]]*\]", raw_message):
        images.append(m.group(1))
    return _strip_cq(text_part), images


# —— 连发防抖(per-user 输入缓冲 + 计时器;搬 V2.0 qq/webhook 同构逻辑)——
_debounce: dict[str, dict] = {}
_debounce_lock = asyncio.Lock()


async def _schedule_debounce(user_id: str, text: str, image_urls: list[str], msg_id: str) -> None:
    """连发防抖:首条启动计时器,期间连发追加缓冲并重置计时器,超时合并走 pipeline(同 webhook)。"""
    async with _debounce_lock:
        state = _debounce.get(user_id)
        if state is None:
            state = {"texts": [text] if text else [], "images": list(image_urls),
                     "msg_id": msg_id, "task": None}
            _debounce[user_id] = state
        else:
            if text:
                state["texts"].append(text)
            state["images"].extend(image_urls)
            state["msg_id"] = msg_id   # 用最新 msg_id
            if state["task"] is not None:
                state["task"].cancel()
        state["task"] = asyncio.create_task(_flush(user_id))


async def _flush(user_id: str) -> None:
    """防抖超时:合并连发输入(文本+图片 vision)→ pipeline → 经 adapter 下发(同 webhook._flush)。"""
    try:
        await asyncio.sleep(settings.input_debounce_sec)
    except asyncio.CancelledError:
        return   # 连发重置取消,不 flush
    async with _debounce_lock:
        state = _debounce.pop(user_id, None)
    if not state:
        return
    parts: list[str] = [t for t in state["texts"] if t]
    if settings.multimodal_vision_enable:   # 审查#6:对齐 webhook(总开关关时跳过 vision)
        for url in state["images"]:
            desc = await _describe_image(url)
            parts.append(f"[用户发了一张图片: {desc}]" if desc else "[用户发了一张图片,但解析失败]")
    combined = "\n".join(parts)
    if not combined:
        return
    ctx = MessageContext(object_id=user_id, user_text=combined,
                         created_ts=int(time.time() * 1000))
    ctx.qq_msg_id = state["msg_id"]   # continuous_send 插件分段门控用(onebot 下 msg_seq 被忽略)
    logger.info("pipeline 处理开始(onebot) user=%s 输入长度=%d", user_id, len(combined))
    try:
        async for _token in run_stream(ctx):
            pass
        reply = ctx.reply_text
        if not reply:
            logger.info("pipeline 未生成回复(onebot) user=%s", user_id)
        elif getattr(ctx, "reply_sent", False):
            logger.info("回复已由插件分段发送(onebot) user=%s", user_id)
        else:
            from adapter import get_current_adapter
            adapter = await get_current_adapter()
            await adapter.send_text(user_id, reply, msg_id=ctx.qq_msg_id)
            logger.info("回复已发送(onebot) user=%s 长度=%d", user_id, len(reply))
    except Exception:
        logger.exception("pipeline 处理失败(onebot) user=%s", user_id)


async def _describe_image(url: str) -> str:
    """图片 vision 描述(NapCat image url 免鉴权直接 GET,软失败返空串)。"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.get(url, follow_redirects=True)
            resp.raise_for_status()
            img_bytes = resp.content
        from modality import get_vision
        vision = get_vision()
        return await vision.understand(img_bytes, settings.multimodal_vision_prompt, "image/jpeg")
    except Exception as e:
        logger.warning("图片 vision 解析失败(onebot,软失败): %s", e)
        return ""
