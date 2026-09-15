"""
表情包库存储层(2026-09-15 表情包收发功能)

设计:入站表情包(image/mface 段)不再以 "[图片]" 占位丢弃,而是——
  ① 下载图片字节存入 server/data/stickers/(文件名=内容 md5,同图重发自动去重);
  ② vision 描述成语义 token "[表情包: 简短描述画面与情绪]"(真实照片则 "[图片: 描述]",
     不入库)——token 进消息 content/pipeline,训练上下文语义完整(用户诉求:占位符上下文不齐);
  ③ 描述缓存 Redis(内容 md5 → token,同图不重复调 vision);表情包注册库 hash
     (mychat:sticker:lib: 文件名 → 描述)供出站匹配。
出站:回复文本中的 [表情包: 描述] token(adapter/onebot.send_text 解析)→ 查库匹配
  → image 段(base64) 发真实表情包;模型经 OUTPUT_CONTRACT 学会用 token,经训练数据
  (手动回复真实表情包 → message_sent 落 token)学会何时用。

mface summary 短路:QQ 商城表情自带 summary(如"[开心]")时免 vision 直接用。

软失败原则:下载/vision 任何失败 → 回退 "[图片]" 占位(链路不断,消息不丢)。

作者: 李文煜
日期: 2026-09-15
"""
import hashlib
import logging
import re
from pathlib import Path

import httpx
from redis.asyncio import Redis

from core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# 表情包库目录(容器内 /app/server/data/stickers,与宿主机 ~/ChatBot-V3/server/data/stickers 挂载互通)
STICKER_DIR: Path = PROJECT_ROOT / "server" / "data" / "stickers"

# Redis 键:描述缓存(内容 md5 → token)/ 库注册(文件名 → 描述)
_K_DESC = "mychat:sticker:desc:{ch}"
_K_LIB = "mychat:sticker:lib"

# vision 描述提示词:要求输出带标签 token,供入库判断与 content 直接使用
_DESC_PROMPT = (
    "这是手机聊天里的一张图片。判断它是表情包还是真实照片:"
    "若是表情包(卡通/梗图/贴图/表情图),输出一行『[表情包: 简短描述画面与情绪]』;"
    "若是真实照片或截图,输出一行『[图片: 简短描述内容]』。"
    "只输出这一行,描述控制在20字内,不要任何多余内容。"
)

# token 解析(入站 vision 输出校验 / 出站回复拆分共用)
_TOKEN_RE = re.compile(r"^[ \t]*\[(表情包|图片)[:：]\s*([^\]]{1,40})\][ \t]*$")
# 出站:回复文本中的表情包 token(独立成段;方括号+冒号,描述限长)
_REPLY_TOKEN_RE = re.compile(r"\[表情包[:：]\s*([^\]]{1,40})\]")

_MAX_DOWNLOAD = 5 * 1024 * 1024   # 下载上限 5MB(表情包都是小图)


def split_reply_with_tokens(text: str) -> list[tuple[str, str]]:
    """把回复文本拆成 [("text", 片段)|("sticker", 描述)] 序列(出站 adapter 用)。
    token 之外的文本原样保留(含换行,分段插件拆行后单行 token 即独立 sticker 段)。"""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in _REPLY_TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        out.append(("sticker", m.group(1).strip()))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return out


def _ext_of(data: bytes, content_type: str) -> str:
    """图片扩展名:魔数优先(gif/png),回退 Content-Type,再回退 jpg"""
    if data[:3] == b"GIF":
        return "gif"
    if data[:8] == bytes.fromhex("89504e470d0a1a0a"):
        return "png"
    ct = (content_type or "").lower()
    if "gif" in ct:
        return "gif"
    if "png" in ct:
        return "png"
    if "webp" in ct:
        return "webp"
    return "jpg"


def _parse_token(vision_out: str) -> tuple[str, str] | None:
    """解析 vision 输出为 (kind, desc);格式不符返 None(回退占位)。"""
    m = _TOKEN_RE.match((vision_out or "").strip().splitlines()[0] if vision_out else "")
    if m:
        return m.group(1), m.group(2).strip()
    # 容错:vision 忽略了外层格式但内容含"表情包"字样时仍按表情包取
    line = (vision_out or "").strip().splitlines()[0] if vision_out else ""
    m2 = re.match(r"^[\[『「]?(表情包|图片)[:：]\s*([^\]』」]{1,40})[\]』」]?$", line)
    return (m2.group(1), m2.group(2).strip()) if m2 else None


async def _download(url: str) -> tuple[bytes, str] | None:
    """下载图片字节(async httpx;超限/失败返 None——QQ 图片 url 直链,ws_client 同款先例)。"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(url, follow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            if len(r.content) > _MAX_DOWNLOAD:
                logger.warning("表情包下载超限跳过(%d bytes)", len(r.content))
                return None
            return r.content, r.headers.get("content-type", "")
    except Exception as e:
        logger.warning("表情包下载失败(软失败回退占位): %s", e)
        return None


async def ingest(redis: Redis, url: str, *, summary: str = "") -> str:
    """入站表情包/图片 → 下载+描述+入库,返回 content token。
    "[表情包: 描述]"(入库)/ "[图片: 描述]"(照片不入库)/ "[图片]"(软失败回退)。
    mface 自带 summary 非空时免 vision 直接采用。"""
    if not url:
        return "[图片]"
    got = await _download(url)
    if got is None:
        return "[图片]" if not summary else f"[表情包: {_clean_summary(summary)}]"
    data, ctype = got
    ch = hashlib.md5(data).hexdigest()[:16]              # 内容 md5:同图重发(签名 url 每次不同)仍命中缓存
    cache_key = _K_DESC.format(ch=ch)
    cached = await redis.get(cache_key)
    if cached:
        return cached
    # mface summary 短路(QQ 官方描述,免 vision 调用)
    if summary and _clean_summary(summary):
        token = f"[表情包: {_clean_summary(summary)}]"
    else:
        token = await _vision_token(data, ctype)
        if token is None:
            return "[图片]"                              # vision 失败:不缓存,下次重试
    # 表情包入库(文件+库注册);照片只缓存 token 不占磁盘
    if token.startswith("[表情包"):
        try:
            STICKER_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"{ch}.{_ext_of(data, ctype)}"
            (STICKER_DIR / fname).write_bytes(data)
            await redis.hset(_K_LIB, fname, token[token.find(":") + 1:token.find("]")].strip())
        except Exception:
            logger.exception("表情包入库写盘/注册失败(不影响 token 返回)")
    await redis.set(cache_key, token)
    return token


def _clean_summary(s: str) -> str:
    """清理 mface summary:去括号/方括号包裹与首尾空白;空串表示不可用。"""
    s = (s or "").strip().strip("[]『』「」()")
    return s[:20].strip()


def _to_png_bytes(data: bytes) -> bytes | None:
    """vision 前归一化为 PNG:gif 取首帧(GLM vision 不支持 image/gif,线上实测 400 code=1210)、
    webp 转码(误存 .jpg 的 webp 同样被拒)。PIL 不可用/解析失败返 None(回退原字节)。"""
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data))
        if getattr(img, "n_frames", 1) > 1:
            img.seek(0)                        # gif:首帧代表内容
        img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


async def _vision_token(data: bytes, ctype: str) -> str | None:
    """vision 描述 → token;失败返 None。gif/webp 先归一化 PNG(见 _to_png_bytes)。"""
    try:
        from modality import get_vision
        from core.config import settings
        if not settings.multimodal_vision_enable:
            return None
        norm = _to_png_bytes(data)
        if norm is not None:
            data, ctype = norm, "image/png"
        vision = get_vision()
        mime = (ctype or "").split(";")[0].strip() or "image/jpeg"
        if not mime.startswith("image/"):
            mime = "image/jpeg"
        out = await vision.understand(data, _DESC_PROMPT, mime)
        parsed = _parse_token(out)
        if not parsed:
            return None
        kind, desc = parsed
        return f"[表情包: {desc}]" if kind == "表情包" else f"[图片: {desc}]"
    except Exception:
        logger.warning("表情包 vision 描述失败(软失败)", exc_info=True)
        return None


async def find_sticker(redis: Redis, desc: str) -> Path | None:
    """按描述匹配库内表情包文件(出站用)。双向子串匹配(忽略大小写);无匹配返 None。
    遍历顺序按文件名排序保证确定性。"""
    d = (desc or "").strip().casefold()
    if not d:
        return None
    lib = await redis.hgetall(_K_LIB)
    for fname in sorted(lib):
        fd = (lib[fname] or "").strip().casefold()
        if fd and (d in fd or fd in d):
            p = STICKER_DIR / fname
            if p.exists():
                return p
    return None


async def register_existing(redis: Redis, limit: int = 200) -> dict:
    """为库目录中未注册的文件补描述并注册(scripts/register_stickers.py 与面板维护用)。
    逐个文件读字节 → 查缓存/调 vision → hset 注册。返回 {registered, skipped, failed}。"""
    if not STICKER_DIR.exists():
        return {"registered": 0, "skipped": 0, "failed": 0}
    lib = await redis.hgetall(_K_LIB)
    registered = skipped = failed = 0
    for p in sorted(STICKER_DIR.iterdir())[:limit]:
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.name in lib:
            skipped += 1
            continue
        try:
            data = p.read_bytes()
            token = await _vision_token(data, "")
            if token and token.startswith("[表情包"):
                desc = token[token.find(":") + 1:token.find("]")].strip()
                await redis.hset(_K_LIB, p.name, desc)
                await redis.set(_K_DESC.format(ch=hashlib.md5(data).hexdigest()[:16]), token)
                registered += 1
            else:
                # 照片/描述失败:不注册(留在目录,不计失败——可能是用户存的真实图片)
                skipped += 1
        except Exception:
            failed += 1
            logger.warning("注册表情包失败 %s", p.name, exc_info=True)
    return {"registered": registered, "skipped": skipped, "failed": failed}


def read_bytes(path: Path) -> bytes:
    """读库文件字节(出站 base64 用;小文件同步读)"""
    return path.read_bytes()
