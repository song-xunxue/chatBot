"""
QQ 官方机器人 Webhook 回调入口(FastAPI 路由)
职责:① Ed25519 验签(防篡改)② 回调地址验证(op=13 握手)③ 事件解析(op=0 Dispatch)
      ④ M1 echo 链路(C2C_MESSAGE_CREATE → 回发)

凭证(只需 AppID + AppSecret;AppSecret 既换 token 又验签,QQ 文档「Bot Secret」即此字段):
  - 密钥派生:seed = AppSecret 翻倍到 ≥32 字节、取前 32 字节 → 用该 seed 派生 Ed25519 确定密钥对
  - 入站事件验签(op=0):用「公钥」验证 X-Signature-Ed25519(64字节 hex) 对 {timestamp}{body} 的签名
  - 回调验证(op=13):用「私钥」对 {event_ts}{plain_token} 签名,回 {plain_token, signature} 握手

签名机制严格对照 QQ 文档「安全和授权」Go DEMO,金标准单测验证通过(密钥派生 pub + op=13 签名)。
payload 通用结构 {op,s,t,d,id};C2C 私聊 op=0 且 t=C2C_MESSAGE_CREATE,d 含 author.user_openid/content/id/timestamp。

M1 echo:收私聊消息 → send_c2c_message(openid, "收到:{content}", msg_id=msg_id)。M2 起替换为 pipeline。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建 webhook:Ed25519 验签 + 回调验证(op=13) + C2C_MESSAGE_CREATE 解析 + echo 链路
  2. 凭证从「AppSecret+BotSecret 双凭证」修正为「单 AppSecret」(用户后台确认无独立 Bot Secret)
"""
import logging
import time

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from core.config import settings
from qq.api_client import send_c2c_message
from qq.types import C2CMessage

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
        raw=event_d,
    )


@router.post("/webhook")
async def qq_webhook(
    request: Request,
    x_signature_ed25519: str = Header(default="", alias="X-Signature-Ed25519"),
    x_signature_timestamp: str = Header(default="", alias="X-Signature-Timestamp"),
):
    """QQ Webhook 回调入口:回调验证(op=13 握手)/ 事件分发(op=0,验签+防重放)。

    QQ 后台配置回调 URL 填 https://<域名>/qq/webhook(端口须 80/443/8080/8443)。
    QQ 要求 3 秒内返 200(M2 接 LLM 慢响应时改 create_task 旁路发 + 立即 200)。

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
        # 防重放:timestamp 与服务器时间差超阈值拒绝(阈值可配 qq_signature_max_skew_sec,默认 300s)
        if abs(time.time() - int(x_signature_timestamp)) > settings.qq_signature_max_skew_sec:
            logger.warning("QQ 回调时间戳超期 ts=%s", x_signature_timestamp)
            return JSONResponse(status_code=401, content={"detail": "timestamp expired"})
    except ValueError:
        return JSONResponse(status_code=401, content={"detail": "invalid timestamp"})
    if not verify_signature(app_secret, x_signature_timestamp, body, x_signature_ed25519):
        logger.warning("QQ 回调验签失败")
        return JSONResponse(status_code=401, content={"detail": "invalid signature"})

    # op=0 Dispatch:事件派发
    if op == 0 and t == "C2C_MESSAGE_CREATE":
        msg = parse_c2c_message(d)
        await _handle_c2c_message(msg)
        return JSONResponse(status_code=200, content={"op": 12})  # op=12 HTTP Callback ACK

    # 其他事件类型(M1 忽略,返 ACK;M2+ 按需扩展 FRIEND_ADD/GROUP_AT_MESSAGE_CREATE 等)
    logger.info("QQ 事件 op=%s t=%s 未处理(M1 仅处理 C2C_MESSAGE_CREATE)", op, t)
    return JSONResponse(status_code=200, content={"op": 12})


async def _handle_c2c_message(msg: C2CMessage) -> None:
    """处理私聊消息。M1 = echo 回发(被动回复带 msg_id);M2 起替换为 pipeline 产出真实回复"""
    try:
        # echo:验证整条 收→验签→解析→token→发 链路通(M2 换 pipeline.run_stream)
        await send_c2c_message(msg.openid, f"收到:{msg.content}", msg_id=msg.msg_id)
    except Exception:
        # 发消息失败不影响 ACK(已返 200 给 QQ);M2 加重试队列
        logger.exception("echo 回发失败 openid=%s", msg.openid)
