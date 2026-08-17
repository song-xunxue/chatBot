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

作者: 李文煜
日期: 2026-08-16
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


def is_connected() -> bool:
    """NapCat 反向WS是否在线(adapter/takeover 判断出站可用)"""
    return _ws is not None


def _dispatch_response(data: dict) -> bool:
    """Action 响应分发:带 echo tag 的响应完成对应 future。返 True=已消费(是响应)。
    (websocket 主循环与单测共用)"""
    echo_tag = str(data.get("echo", "")) if isinstance(data, dict) else ""
    if echo_tag and ("status" in data or "retcode" in data):
        fut = _pending.get(echo_tag)
        if fut and not fut.done():
            fut.set_result(data)
        return True
    return False


async def call_action(action: str, params: dict, timeout: float | None = None) -> dict | None:
    """经接管号连接发 OneBot Action,等响应(echo tag 匹配)。
    timeout 默认 settings.onebot_call_timeout(审查#4 接线,原先硬编码 5s);
    超时返 None(软降级,调用方按失败处理);未连接抛 RuntimeError。"""
    global _seq
    if _ws is None:
        raise RuntimeError("NapCat 未连接(onebot 反向WS未建立)")
    if timeout is None:
        timeout = settings.onebot_call_timeout
    _seq += 1
    tag = f"act-{_seq}"
    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    _pending[tag] = fut
    try:
        await _ws.send_text(json.dumps({"action": action, "params": params, "echo": tag}))
        return await asyncio.wait_for(fut, timeout)
    except asyncio.TimeoutError:
        logger.warning("onebot action 响应超时 action=%s(NapCat 可能被风控拒发)", action)
        return None
    finally:
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
    """OneBot 事件分发:只处理接管号(self_id 过滤)的私聊消息,其余记日志忽略。"""
    sid = str(data.get("self_id", ""))
    if settings.onebot_self_id and sid != settings.onebot_self_id:
        return   # 非接管号(双号场景另一号连入),忽略
    pt = data.get("post_type")
    if pt == "meta_event":
        if data.get("meta_event_type") == "lifecycle":
            logger.info("onebot lifecycle: 接管号 %s 已连接", sid)
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
        pid = await takeover_store.enqueue(redis, user_id,
                                           user_text=text, msg_id=msg_id)
        logger.info("代答模式入队(onebot) user=%s pid=%s", user_id, pid)
        return
    await _schedule_debounce(user_id, text, image_urls, msg_id)


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
