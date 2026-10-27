"""
表情包库管理 REST 接口(2026-10-25,sticker_plus 插件配套):库列表/上传/删除/重跑描述/文字表情渲染。
库数据 = Redis hash mychat:sticker:lib(文件名 → 描述)+ server/data/stickers 目录文件;
存储层走 storage/sticker_store.py 追加的库管理函数,渲染走 plugins/sticker_plus/render 共用入口。

路由(prefix /api/v1,全部 X-Access-Token 鉴权):
  GET    /sticker/list                列全库 [{file, desc, size, last_used, exists}]
  POST   /sticker/upload              上传入库(body data_base64 必填;desc 空走 vision 自动描述)
  DELETE /sticker/{name}              删库条目 + 物理文件(不存在 404)
  POST   /sticker/{name}/describe     对已有文件重跑 vision 描述并更新注册(失败 400)
  POST   /sticker/render              文字表情生成(body text 必填/template 可选底图)

日期: 2026-10-25

2026-10-25
变更说明：
  1. 新建:5 端点;upload 走 base64 请求体(超限/非法名/非法 base64 → 400),vision 判非
     表情包时文件已存但 registered=False 带 warning(不 4xx);render 转 render_text_sticker,
     ValueError → 400(参数)、RuntimeError → 503(Pillow 未装)
  2. 审查加固:upload 解码前限长 7MB(base64 膨胀 4/3,防大请求体内存放大);render 请求体
     增 font/font_size/stroke_width/position 渲染覆盖项(plugin.yaml 的 render_* 配置经面板
     预填传此);异常链补 from e;文字描述注明底图 templates/ 白名单约束
"""
import base64
import binascii

from fastapi import APIRouter, Body, Depends, HTTPException

from api._auth import verify_token
from plugins.sticker_plus.render import render_text_sticker
from storage import sticker_store
from storage.redis_client import get_redis

router = APIRouter(prefix="/api/v1", tags=["sticker"])


@router.get("/sticker/list", dependencies=[Depends(verify_token)])
async def list_stickers():
    """列全库(含 size/last_used/exists,按文件名排序)——供 sticker_plus 面板库管理页展示"""
    redis = await get_redis()
    return {"items": await sticker_store.list_library(redis)}


@router.post("/sticker/upload", dependencies=[Depends(verify_token)])
async def upload_sticker(body: dict = Body(...)):
    """上传图片入库:body {data_base64 必填, name 可选(缺省=内容 md5 命名), desc 可选(空走 vision)}。
    超限/非法名/非法 base64 → 400;vision 判非表情包 → 200 registered=False 带 warning。"""
    raw = str(body.get("data_base64", "") or "")
    if not raw:
        raise HTTPException(status_code=400, detail="data_base64 缺失或非法")
    if len(raw) > 7 * 1024 * 1024:
        # 解码前限长:base64 膨胀 4/3(5MB 图 ≈ 6.8MB 文本),先挡大包再解码,防内存放大
        raise HTTPException(status_code=400, detail="data_base64 超过 7MB 上限")
    try:
        # b64decode(字符串, validate=True):非 base64 字母表字符(含空白)直接抛 binascii.Error
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=400, detail="data_base64 缺失或非法") from e
    if not data:
        raise HTTPException(status_code=400, detail="上传内容为空")
    redis = await get_redis()
    try:
        return await sticker_store.save_upload(redis, data,
                                               name=str(body.get("name", "") or ""),
                                               desc=str(body.get("desc", "") or ""))
    except ValueError as e:   # 超限 / 魔数 / 文件名白名单 / 描述校验不通过
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/sticker/{name}", dependencies=[Depends(verify_token)])
async def delete_sticker(name: str):
    """删库:hdel 注册 + 最近使用,删物理文件;名字非法或库与磁盘都不存在 → 404"""
    redis = await get_redis()
    if not await sticker_store.remove_sticker(redis, name):
        raise HTTPException(status_code=404, detail="表情包不存在")
    return {"deleted": name}


@router.post("/sticker/{name}/describe", dependencies=[Depends(verify_token)])
async def describe_sticker(name: str):
    """对已有文件重跑 vision 描述并更新注册(描述改错时手动刷新用);失败/判非表情包 → 400"""
    redis = await get_redis()
    desc = await sticker_store.describe_sticker(redis, name)
    if desc is None:
        raise HTTPException(status_code=400, detail="vision 描述失败或判定为非表情包")
    return {"name": name, "desc": desc}


@router.post("/sticker/render", dependencies=[Depends(verify_token)])
async def render_sticker(body: dict = Body(...)):
    """文字表情生成:body {text 必填, template 可选(底图,仅允许库目录 templates/ 白名单内,
    白名单外/损坏一律回退纯色画布), font/font_size/stroke_width/position 可选(渲染覆盖项,
    缺省用 render 模块默认;面板可由 sticker_plus 的 render_* 配置预填)} → {token, file, desc}。
    与插件发送共用 render_text_sticker(同文字同底图幂等覆盖)。"""
    text = str(body.get("text", "") or "")
    template = str(body.get("template", "") or "")

    def _int_or_400(key: str, default: int) -> int:
        """取整型覆盖项;空/缺省用默认,非整数 → 400(防 int() 抛 TypeError 变 500)"""
        v = body.get(key)
        if v is None or v == "":
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{key} 须为整数")

    redis = await get_redis()
    try:
        return await render_text_sticker(
            redis, text, template,
            font=str(body.get("font", "") or ""),
            font_size=_int_or_400("font_size", 0),
            stroke_width=_int_or_400("stroke_width", -1),
            position=str(body.get("position", "bottom") or "bottom"),
        )
    except ValueError as e:        # 文字空/超长、参数问题
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:      # Pillow 未装(渲染环境不可用)
        raise HTTPException(status_code=503, detail=str(e)) from e
