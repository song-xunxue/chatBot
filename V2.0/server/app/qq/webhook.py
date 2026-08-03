"""
QQ 官方机器人 Webhook 回调入口(FastAPI 路由)
职责:① Ed25519 验签(防篡改)② 回调地址验证(op=13 握手)③ 事件解析(op=0 Dispatch)
      ④ M2 pipeline 链路(C2C_MESSAGE_CREATE → 防抖合并 → pipeline → 被动回复)

凭证(只需 AppID + AppSecret;AppSecret 既换 token 又验签,QQ 文档「Bot Secret」即此字段):
  - 密钥派生:seed = AppSecret 翻倍到 ≥32 字节、取前 32 字节 → 用该 seed 派生 Ed25519 确定密钥对
  - 入站事件验签(op=0):用「公钥」验证 X-Signature-Ed25519(64字节 hex) 对 {timestamp}{body} 的签名
  - 回调验证(op=13):用「私钥」对 {event_ts}{plain_token} 签名,回 {plain_token, signature} 握手

签名机制严格对照 QQ 文档「安全和授权」Go DEMO,金标准单测验证通过(M1a)。
payload 通用结构 {op,s,t,d,id};C2C 私聊 op=0 且 t=C2C_MESSAGE_CREATE,d 含 author.user_openid/content/id/timestamp。

M2 链路(替换 M1a echo):
  - QQ 要求 3 秒内返 200,而 pipeline 调 LLM 慢 → 收消息立即 ACK,防抖+pipeline 旁路 asyncio.create_task
  - 连发防抖(input_debounce_sec):用户连发多条合并为一次 LLM 调用(避免 N 条=N 次 LLM+记忆+评分)
  - 超时合并 → pipeline.run_stream → 累积完整回复 → send_c2c_message 被动回复(带 msg_id)

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建 webhook:Ed25519 验签 + 回调验证(op=13) + C2C_MESSAGE_CREATE 解析 + echo 链路
  2. 凭证从「AppSecret+BotSecret 双凭证」修正为「单 AppSecret」

2026-06-27
变更说明：
  1. M2 echo → pipeline:连发防抖合并 + run_stream + 被动回复;改旁路 task 立即 ACK(满足 QQ 3s)

2026-06-30
变更说明：
  1. M8 代答联动:C2C_MESSAGE_CREATE 分支先查代答开关,开启则入 takeover pending 队列
     (逐条入队,不合并连发,管理员面板看到完整原话),不进 pipeline;关闭则原防抖 → pipeline

2026-07-07
变更说明：
  1. continuous_send 支持:_flush 填 ctx.qq_msg_id(被动回复 msg_id 供插件分段用)
     + 下发前检查 ctx.reply_sent(插件已分段发则跳过默认单条下发)

2026-08-04
变更说明：
  1. 补关键链路 info 日志(logging 盲区修复配套):收到 C2C 消息 / pipeline 处理开始 / 回复已发送 / 插件分段 / 未生成回复
"""
import asyncio
import logging
import time

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from core.config import settings
from qq.api_client import send_c2c_message, send_download
from qq.types import C2CMessage
from pipeline.context import MessageContext
from pipeline.runner import run_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qq", tags=["qq-webhook"])

_SEED_SIZE = 32  # Ed25519 seed 固定 32 字节(对应 Go ed25519.SeedSize)


def _derive_seed(app_secret: str) -> bytes:
    """派生 32 字节 Ed25519 seed(严格对照 QQ 官方 Go DEMO:secret 翻倍到 ≥32 字节后取前 32)"""
    seed = app_secret.encode("utf-8")
    while len(seed) < _SEED_SIZE:
        seed = seed * 2  # Go DEMO: strings.Repeat(seed, 2)
    return seed[:_SEED_SIZE]


def _keypair(app_secret: str) -> tuple[bytes, bytes]:
    """由 AppSecret 派生确定的 Ed25519 公钥/私钥(对照 Go ed25519.GenerateKey(seed))"""
    sk = SigningKey(_derive_seed(app_secret))
    return bytes(sk.verify_key), bytes(sk)  # (32B 公钥, 64B 私钥=seed+pub)


def verify_signature(app_secret: str, timestamp: str, body: bytes, signature_hex: str) -> bool:
    """验证入站事件签名(op=0):公钥验 {timestamp}{body}。失败返 False(防篡改/防伪造)。

    官方 DEMO:secret=naOC0ocQE3shWLAfffVLB1rhYPG7, ts=1725442341,
    body 含 op=0 → 签名验证通过(密钥派生金标准单测 test_publickey_matches_official_demo 覆盖)。
    """
    pub_key_bytes, _ = _keypair(app_secret)
    try:
        verify_key = VerifyKey(pub_key_bytes)
        message = timestamp.encode("utf-8") + body  # 按 timestamp+body 顺序拼接(官方 Go: msg.WriteString(ts)+Write(body))
        verify_key.verify(message, bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError):
        return False


def sign_validation(app_secret: str, event_ts: str, plain_token: str) -> str:
    """回调地址验证(op=13)签名:私钥签 {event_ts}{plain_token}。返 hex 签名。

    官方 DEMO:secret=DG5g3B4j9X2KOErG, plain_token=Arq0D5A61EgUu4OxUvOp,
    event_ts=1725442341 → 签名 87befc99...c706(金标准单测 test_sign_validation_matches_official_demo 覆盖)。
    """
    _, priv_key_bytes = _keypair(app_secret)
    signing_key = SigningKey(priv_key_bytes[:_SEED_SIZE])  # nacl 私钥取前 32 字节 seed 构造(等价 Go privateKey)
    message = event_ts.encode("utf-8") + plain_token.encode("utf-8")
    return signing_key.sign(message).signature.hex()


def parse_c2c_message(event_d: dict) -> C2CMessage:
    """解析 C2C_MESSAGE_CREATE 事件 d(字段路径对照 QQ 文档「事件」)"""
    author = event_d.get("author", {}) or {}
    return C2CMessage(
        openid=author.get("user_openid", ""),   # 发送者 openid(本项目作 object_id)
        content=event_d.get("content", ""),     # 文本内容
        msg_id=event_d.get("id", ""),           # 平台方消息 id(被动回复必带)
        timestamp=event_d.get("timestamp", ""),  # RFC3339 时间
        attachments=event_d.get("attachments", []) or [],  # 媒体附件(M-vision 图片解析用)
        raw=event_d,
    )


# —— 连发防抖状态(per-object 输入缓冲 + 计时器)——
# oid -> {"texts": list[str], "msg_id": str, "task": asyncio.Task}
_debounce: dict[str, dict] = {}
_debounce_lock = asyncio.Lock()


async def _schedule_debounce(msg: C2CMessage) -> None:
    """连发防抖:首条启动计时器,期间连发追加缓冲并重置计时器,超时合并走 pipeline。
    快速(仅 dict+lock,不跑 LLM),保证 webhook 立即 ACK。"""
    async with _debounce_lock:
        state = _debounce.get(msg.openid)
        if state is None:
            state = {"texts": [msg.content], "msgs": [msg], "msg_id": msg.msg_id, "task": None}
            _debounce[msg.openid] = state
        else:
            state["texts"].append(msg.content)
            state["msgs"].append(msg)            # 完整 msg(含 attachments,M-vision 图片解析用)
            state["msg_id"] = msg.msg_id   # 用最新 msg_id(被动回复 60min 窗口)
            if state["task"] is not None:
                state["task"].cancel()      # 连发重置计时器
        state["task"] = asyncio.create_task(_flush(msg.openid))


async def _resolve_msg_text(msg: C2CMessage) -> str:
    """解析单条消息为 pipeline 输入文本:文本内容 + 图片附件的 GLM vision 描述。
    图片解析全程软失败(失败返空串,不阻塞 pipeline)。"""
    parts = []
    if msg.content:
        parts.append(msg.content)
    if settings.multimodal_vision_enable and msg.attachments:
        for att in msg.attachments:
            if str(att.get("content_type", "")).startswith("image"):
                desc = await _describe_image(att)
                if desc:
                    parts.append(f"[用户发了一张图片: {desc}]")
                else:
                    parts.append("[用户发了一张图片,但解析失败]")
    return "\n".join(parts)


async def _describe_image(att: dict) -> str:
    """下载图片 + GLM vision 解析,返描述。任意步骤失败返空串(软失败)。"""
    try:
        url = att.get("url", "") or att.get("file_url", "")
        if not url:
            return ""
        img_bytes = await send_download(url)   # QQ 附件需鉴权下载
        if not img_bytes:
            return ""
        from modality import get_vision
        vision = get_vision()
        mime = _guess_image_mime(att.get("filename", "") or att.get("content_type", ""))
        return await vision.understand(img_bytes, settings.multimodal_vision_prompt, mime)
    except Exception as e:
        logger.warning("图片 vision 解析失败(软失败,跳过): %s", e)
        return ""


def _guess_image_mime(hint: str) -> str:
    """据文件名/content_type 猜 MIME(vision provider base64 编码用)"""
    h = hint.lower()
    if "png" in h:
        return "image/png"
    if "gif" in h:
        return "image/gif"
    if "webp" in h:
        return "image/webp"
    return "image/jpeg"


async def _flush(openid: str) -> None:
    """防抖超时:合并连发输入 → pipeline.run_stream → 被动回复。
    被连发重置 cancel 时不 flush(state 留给新 task)。"""
    try:
        await asyncio.sleep(settings.input_debounce_sec)
    except asyncio.CancelledError:
        return   # 连发重置取消,不 flush
    async with _debounce_lock:
        state = _debounce.pop(openid, None)
    if not state:
        return
    # 解析每条消息为文本(文本内容 + 图片附件 vision 描述),合并为一次 pipeline 输入
    parts = []
    for m in state["msgs"]:
        t = await _resolve_msg_text(m)
        if t:
            parts.append(t)
    combined = "\n".join(parts) if parts else "\n".join(state["texts"])   # 兜底:全空用原始 texts
    msg_id = state["msg_id"]
    ctx = MessageContext(object_id=openid, user_text=combined,
                         created_ts=int(time.time() * 1000))
    ctx.qq_msg_id = msg_id   # 被动回复 msg_id(continuous_send 插件分段发送用,2026-07-07)
    logger.info("pipeline 处理开始 oid=%s 消息数=%d 输入长度=%d", openid, len(state["msgs"]), len(combined))
    try:
        # QQ 不逐 token 发,迭代生成器仅为驱动管道跑完 + 累积 reply_text
        async for _token in run_stream(ctx):
            pass
        reply = ctx.reply_text
        if not reply:
            # pipeline 未生成回复(如 tool-loop 决定不答 / LLM 返空),记录便于排障
            logger.info("pipeline 未生成回复 oid=%s", openid)
        elif getattr(ctx, "reply_sent", False):
            # continuous_send 插件已分段发(reply_sent=True),跳过默认单条下发(2026-07-07)
            logger.info("回复已由插件分段发送 oid=%s", openid)
        else:
            # 默认单条下发;出站守卫(#3)已下沉到 send_c2c_message(机器产出默认过守卫),此处直接发
            # 被动回复带 msg_id(60min 窗口/4 次);超时或超次 QQ 拒绝,M2 单测 mock 不触发,M9 真实场景注意
            await send_c2c_message(openid, reply, msg_id=msg_id)
            logger.info("被动回复已发送 oid=%s 回复长度=%d", openid, len(reply))
    except Exception:
        logger.exception("pipeline 处理失败 openid=%s", openid)


@router.post("/webhook")
async def qq_webhook(
    request: Request,
    x_signature_ed25519: str = Header(default="", alias="X-Signature-Ed25519"),
    x_signature_timestamp: str = Header(default="", alias="X-Signature-Timestamp"),
):
    """QQ Webhook 回调入口:回调验证(op=13 握手)/ 事件分发(op=0,验签+防重放)。

    QQ 后台配置回调 URL 填 https://<域名>/qq/webhook(端口须 80/443/8080/8443)。
    QQ 要求 3 秒内返 200:C2C 消息旁路 create_task 防抖+pipeline,立即返 ACK。

    两类回调:
      - op=13 回调地址验证(首次配置):无签名头,服务端用私钥签 event_ts+plain_token 回包证明持有 AppSecret
      - op=0 等普通事件:必带 X-Signature-* 头,公钥验签 timestamp+body + 防重放
    """
    app_secret = settings.qq_app_secret
    if not app_secret:
        logger.warning("QQ_APP_SECRET 未配置,拒绝回调")
        return JSONResponse(status_code=401, content={"detail": "app secret not configured"})

    body = await request.body()  # 原始 bytes,验签必须用未解析的原始 body
    payload = await request.json()
    op = payload.get("op")
    t = payload.get("t")
    d = payload.get("d") or {}

    # op=13 回调地址验证(无签名头):私钥签 event_ts+plain_token 回包,完成握手(对照 QQ 文档 DEMO)
    if op == 13:
        plain_token = d.get("plain_token", "")
        event_ts = d.get("event_ts", "")
        signature = sign_validation(app_secret, event_ts, plain_token)
        return {"plain_token": plain_token, "signature": signature}

    # 其余事件:强制验签 + 防重放
    if not x_signature_ed25519 or not x_signature_timestamp:
        logger.warning("QQ 回调缺签名头 op=%s", op)
        return JSONResponse(status_code=401, content={"detail": "missing signature"})
    try:
        # 防重放:timestamp 与服务器时间差超阈值拒绝(阈值 qq_signature_max_skew_sec,默认 300s)
        if abs(time.time() - int(x_signature_timestamp)) > settings.qq_signature_max_skew_sec:
            logger.warning("QQ 回调时间戳超期 ts=%s", x_signature_timestamp)
            return JSONResponse(status_code=401, content={"detail": "timestamp expired"})
    except ValueError:
        return JSONResponse(status_code=401, content={"detail": "invalid timestamp"})
    if not verify_signature(app_secret, x_signature_timestamp, body, x_signature_ed25519):
        logger.warning("QQ 回调验签失败")
        return JSONResponse(status_code=401, content={"detail": "invalid signature"})

    # op=0 Dispatch:C2C 私聊消息 → 代答拦截 / 防抖合并 → pipeline(旁路,立即 ACK)
    if op == 0 and t == "C2C_MESSAGE_CREATE":
        msg = parse_c2c_message(d)
        logger.info("收到 C2C 消息 oid=%s", msg.openid)
        # M8 代答联动:代答模式开启则入 pending 队列等管理员代答,不进 pipeline
        from storage import takeover_store
        from storage.redis_client import get_redis
        redis = await get_redis()
        if await takeover_store.is_enabled(redis, msg.openid):
            pid = await takeover_store.enqueue(redis, msg.openid,
                                               user_text=msg.content, msg_id=msg.msg_id)
            logger.info("代答模式入队 oid=%s pid=%s", msg.openid, pid)
            return JSONResponse(status_code=200, content={"op": 12})
        await _schedule_debounce(msg)   # 快速:加缓冲+重置计时器,不跑 LLM
        return JSONResponse(status_code=200, content={"op": 12})  # op=12 HTTP Callback ACK

    # 其他事件类型(M2 忽略,返 ACK;后续按需扩展 FRIEND_ADD/GROUP_AT_MESSAGE_CREATE 等)
    logger.info("QQ 事件 op=%s t=%s 未处理(M2 仅处理 C2C_MESSAGE_CREATE)", op, t)
    return JSONResponse(status_code=200, content={"op": 12})
