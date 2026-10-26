"""
sticker_plus 文字表情包渲染(PIL 在底图上叠字,仿 DSH 的 meme_render)

功能:把一段文字叠到指定底图(缺省时自动生成深灰底白字画布)上,生成 PNG 存入表情包库
并注册描述,返回 [表情包: 描述] token——插件发送与 REST /api/v1/sticker/render(面板调试)
共用本模块;文件名 = render_{md5(文字+底图名)[:16]}.png,同文字同底图幂等覆盖(天然去重)。

作者: 李文煜
日期: 2026-10-25

2026-10-25
变更说明：
  1. 新建:render_text_sticker 主入口 + _render_png(PIL 渲染主体) + _wrap_lines(折行);
     字号/描边/位置可调,注册 mychat:sticker:lib 并记 mychat:sticker:last_used
  2. 审查加固:底图白名单(仅 STICKER_DIR/templates/ 内,防 REST 任意路径读图入库外发)、
     损坏底图回退画布(原会 500)、PIL 渲染移线程池(asyncio.to_thread 防阻塞事件循环)、
     小底图自动纵向扩画布(原顶部行会被裁出画布)、md5 键改底图全路径(不同目录同名底图
     原会互相覆盖)、_K_LAST_USED 收敛为 sticker_store 单源定义(本模块导入复用)
"""
import asyncio
import hashlib
import io
import logging
from datetime import datetime
from pathlib import Path

from redis.asyncio import Redis

from storage.sticker_store import STICKER_DIR, _K_LAST_USED, _K_LIB

logger = logging.getLogger(__name__)

# 渲染默认参数(调用方未指定/非法时兜底;插件经 config_schema、REST 经请求体覆盖)
DEFAULT_FONT = "C:/Windows/Fonts/msyh.ttc"   # 微软雅黑(ttc 集合字体;Linux 容器部署需另行挂载字体并配置)
DEFAULT_FONT_SIZE = 48                        # 字号(像素)
DEFAULT_STROKE = 2                            # 描边宽度(像素,0=不描边)
DEFAULT_CANVAS = (480, 480)                   # 无底图时的画布尺寸(宽, 高)
_VALID_POSITIONS = ("top", "center", "bottom")


async def render_text_sticker(redis: Redis, text: str, template: str = "", *,
                              font: str = "", font_size: int = 0,
                              stroke_width: int = -1, position: str = "bottom") -> dict:
    """在底图上叠字生成文字表情包,存库+注册,返回 {file, token, desc}。

    参数:
      redis: 库注册用;template: 底图路径(空/不存在 → 自动生成深灰底画布并 warning);
      font: 字体路径(空=默认微软雅黑;加载失败回退 PIL 默认位图字体并 warning);
      font_size: 字号(0=默认 48);stroke_width: 描边像素(-1=默认 2,0=不描边);
      position: 文字位置 top/center/bottom(非法值回退 bottom)。
    异常:文字空或超 40 字抛 ValueError(token 描述上限);Pillow 未安装抛 RuntimeError。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("文字内容不能为空")
    if len(text) > 40:
        raise ValueError("文字长度不能超过 40 字(表情包 token 描述上限)")
    position = position if position in _VALID_POSITIONS else "bottom"
    # PIL 渲染是同步 CPU 操作,丢线程池执行(asyncio.to_thread:在线程里跑同步函数并 await 结果),
    # 避免大底图/大字号时阻塞事件循环(QQ WS 心跳/其他请求不被卡住)
    fname, png = await asyncio.to_thread(_render_png, text, template, font=font,
                                         font_size=font_size, stroke_width=stroke_width,
                                         position=position)
    STICKER_DIR.mkdir(parents=True, exist_ok=True)
    (STICKER_DIR / fname).write_bytes(png)
    # 注册库(hash: 文件名 → 描述)+ 记最近使用(供库管理 REST 的"最近使用"列展示)
    desc = text
    await redis.hset(_K_LIB, fname, desc)
    await redis.hset(_K_LAST_USED, fname, datetime.now().isoformat(timespec="seconds"))
    logger.info("文字表情包已生成并注册 file=%s desc=%s", fname, desc)
    return {"file": fname, "token": f"[表情包: {desc}]", "desc": desc}


def _render_png(text: str, template: str, *, font: str, font_size: int,
                stroke_width: int, position: str) -> tuple[str, bytes]:
    """PIL 渲染主体(同步纯函数):返回 (文件名, PNG 字节)。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        raise RuntimeError("Pillow 未安装,无法渲染文字表情包(pip install pillow)") from e
    # 1. 底图白名单:仅允许 STICKER_DIR/templates/ 内的文件(防 REST 传任意服务器路径
    #    读图入库外发);不在白名单/不存在/无法解码 → 回退深灰画布(仿表情包:深底白字黑描边)
    tpl_key = ""
    base = None
    if template:
        cand = Path(template)
        root = (STICKER_DIR / "templates").resolve()
        try:
            # is_relative_to(路径):py3.9+ 判断是否仍在白名单目录内(先 resolve 抵消 ../ 逃逸)
            inside = cand.is_file() and cand.resolve().is_relative_to(root)
        except OSError:
            inside = False
        if inside:
            try:
                base = Image.open(cand).convert("RGB")   # open(路径) 读图;convert("RGB") 归一化透明通道
                tpl_key = str(cand.resolve())            # 全路径入 md5 键:不同目录同名底图不互相覆盖
            except OSError:                              # 含 UnidentifiedImageError(损坏/非图片,原会 500)
                logger.warning("文字表情包底图无法解码,回退纯色画布: %s", template)
                base = None
        else:
            logger.warning("文字表情包底图不在白名单目录(%s)或不存在,回退纯色画布: %s", root, template)
    if base is None:
        base = Image.new("RGB", DEFAULT_CANVAS, (64, 64, 64))   # new(模式, (宽,高), 颜色元组)
    draw = ImageDraw.Draw(base)                 # Draw(图) 创建绘制对象
    # 2. 字体:truetype(路径, 字号) 加载矢量字体;失败回退 PIL 内置位图字体(不缩放,仅保可用)
    size = int(font_size) if font_size and int(font_size) > 0 else DEFAULT_FONT_SIZE
    try:
        f = ImageFont.truetype(font or DEFAULT_FONT, size)
    except OSError:
        logger.warning("文字表情包字体加载失败,回退默认字体: %s", font or DEFAULT_FONT)
        f = ImageFont.load_default()
    stroke = int(stroke_width) if stroke_width is not None and int(stroke_width) >= 0 else DEFAULT_STROKE
    # 3. 文字布局:尊重显式 \n,单行超 8 字硬折(表情包短句习惯);行高 1.25 倍字号
    lines = _wrap_lines(text, 8)
    line_h = int(size * 1.25)
    w, h = base.size
    margin = int(h * 0.06)
    total_h = line_h * len(lines)
    if total_h + margin * 2 > h:
        # 底图放不下全部文字:纵向扩展画布(原底图贴顶部,余下用底色补齐),避免顶部行画出画布被裁
        extended = Image.new("RGB", (w, total_h + margin * 2), (64, 64, 64))
        extended.paste(base, (0, 0))            # paste(图, (x, y)):把原底图贴到扩展画布左上角
        base, h, draw = extended, total_h + margin * 2, ImageDraw.Draw(extended)
    if position == "top":
        y = margin
    elif position == "center":
        y = (h - total_h) // 2
    else:                                       # bottom:贴底留 6% 边距
        y = h - total_h - margin
    for line in lines:
        # text((x,y), 文字, font, fill 字色, stroke_width 描边宽, stroke_fill 描边色,
        # anchor="ma" = 水平居中/顶到 ascender,逐行向下画)
        draw.text((w // 2, y), line, font=f, fill=(255, 255, 255),
                  stroke_width=stroke, stroke_fill=(0, 0, 0), anchor="ma")
        y += line_h
    # 4. 导出 PNG 字节(BytesIO 内存缓冲,save(buf, format="PNG"));文件名含底图名 → 同文字
    #    换底图会生成新文件,同文字同底图幂等覆盖(天然去重)
    buf = io.BytesIO()
    base.save(buf, format="PNG")
    ch = hashlib.md5(f"{text}|{tpl_key}".encode("utf-8")).hexdigest()[:16]
    return f"render_{ch}.png", buf.getvalue()


def _wrap_lines(text: str, width: int) -> list[str]:
    """折行:先按显式换行拆,再对超宽行按字符硬折(中文无空格分词,按字符数计)。"""
    out: list[str] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        while len(raw) > width:
            out.append(raw[:width])
            raw = raw[width:]
        if raw:
            out.append(raw)
    return out or [text[:width]]
