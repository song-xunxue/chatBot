"""
rest_sticker REST 单测(2026-10-25,sticker_plus 配套):表情包库管理 5 端点。
覆盖:鉴权 401 / 空库 list / upload(显式 desc、vision 自动描述、判非表情包只存不注册、
非法 base64、非法文件名、超 5MB)/ delete(成功+物理删除+库消失、不存在 404、路径穿越样例非 200)/
describe(vision 成功更新注册、失败 400)/ render(生成+注册+token、空白文字 400)。
fakeredis + monkeypatch STICKER_DIR 到 tmp_path(render 模块按值持有 STICKER_DIR,须一并 patch)。

日期: 2026-10-25
"""
import base64

import httpx
from fastapi import FastAPI

import plugins.sticker_plus.render as render_mod
import storage.redis_client as redis_client
import storage.sticker_store as ss
from api.rest_sticker import router as sticker_router
from core.config import settings

_H = {"X-Access-Token": "t-token"}

# 假 PNG 字节(魔数头 89504e47... → _ext_of 判 .png;内容随意)
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _b64(data: bytes) -> str:
    """bytes → base64 字符串(上传请求体用)"""
    return base64.b64encode(data).decode()


def _wire(monkeypatch, fake, tmp_path):
    """搭独立 app + fakeredis + 库目录指到 tmp_path(render 模块按值持有 STICKER_DIR 副本,须一并 patch)"""
    monkeypatch.setattr(redis_client, "_redis", fake)
    monkeypatch.setattr(settings, "access_token", "t-token")
    monkeypatch.setattr(ss, "STICKER_DIR", tmp_path)
    monkeypatch.setattr(render_mod, "STICKER_DIR", tmp_path)
    app = FastAPI()
    app.include_router(sticker_router)
    return app, fake


async def _ac(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


# ================ 鉴权 / list ================

async def test_list_requires_token(monkeypatch, fake_redis, tmp_path):
    """无 token → 401"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        assert (await ac.get("/api/v1/sticker/list")).status_code == 401


async def test_list_empty(monkeypatch, fake_redis, tmp_path):
    """空库 → items 空列表"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.get("/api/v1/sticker/list", headers=_H)
        assert r.status_code == 200
        assert r.json() == {"items": []}
        assert not await fake.hgetall("mychat:sticker:lib")


async def test_list_fields(monkeypatch, fake_redis, tmp_path):
    """list 字段齐全:desc/size/last_used/exists;缺文件 exists False size 0"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    (tmp_path / "a.gif").write_bytes(b"GIF89aCAT")
    await fake.hset("mychat:sticker:lib", "a.gif", "猫猫开心")
    await fake.hset("mychat:sticker:lib", "ghost.png", "幽灵")   # 无物理文件
    await fake.hset("mychat:sticker:last_used", "a.gif", "2026-10-25T12:00:00")
    async with await _ac(app) as ac:
        items = (await ac.get("/api/v1/sticker/list", headers=_H)).json()["items"]
    by_name = {it["file"]: it for it in items}
    assert by_name["a.gif"] == {"file": "a.gif", "desc": "猫猫开心", "size": 9,
                                "last_used": "2026-10-25T12:00:00", "exists": True}
    assert by_name["ghost.png"]["exists"] is False and by_name["ghost.png"]["size"] == 0


# ================ upload ================

async def test_upload_with_desc_then_visible(monkeypatch, fake_redis, tmp_path):
    """显式 desc 上传 → registered True;list 能看到(size>0、desc 正确、exists)"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/upload", headers=_H,
                          json={"data_base64": _b64(_PNG), "desc": "猫猫点头"})
        assert r.status_code == 200
        j = r.json()
        assert j["registered"] is True and j["desc"] == "猫猫点头"
        assert j["file"].endswith(".png")            # 魔数判扩展名
        items = (await ac.get("/api/v1/sticker/list", headers=_H)).json()["items"]
        assert len(items) == 1
        it = items[0]
        assert it["file"] == j["file"] and it["desc"] == "猫猫点头"
        assert it["size"] == len(_PNG) and it["exists"] is True


async def test_upload_vision_auto_desc(monkeypatch, fake_redis, tmp_path):
    """desc 留空 + vision 返表情包 token → 注册成功,desc 取自 token"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)

    async def fake_vision(data, ctype):
        return "[表情包: 测试图]"

    monkeypatch.setattr(ss, "_vision_token", fake_vision)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/upload", headers=_H, json={"data_base64": _b64(_PNG)})
        assert r.status_code == 200
        j = r.json()
        assert j["registered"] is True and j["desc"] == "测试图"
        assert (tmp_path / j["file"]).exists()


async def test_upload_vision_not_sticker(monkeypatch, fake_redis, tmp_path):
    """vision 返 None(照片/失败)→ 文件已存但 registered False 带 warning,不注册"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)

    async def fake_vision(data, ctype):
        return None

    monkeypatch.setattr(ss, "_vision_token", fake_vision)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/upload", headers=_H, json={"data_base64": _b64(_PNG)})
        assert r.status_code == 200
        j = r.json()
        assert j["registered"] is False and j["desc"] == "" and "warning" in j
        assert list(tmp_path.iterdir())              # 文件已写盘
        assert not await fake.hgetall("mychat:sticker:lib")   # 未注册


async def test_upload_bad_base64(monkeypatch, fake_redis, tmp_path):
    """缺字段/非法 base64(validate 拒非字母表字符)→ 400"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/sticker/upload", headers=_H,
                              json={})).status_code == 400
        assert (await ac.post("/api/v1/sticker/upload", headers=_H,
                              json={"data_base64": "!!!not-base64!!!"})).status_code == 400
        assert (await ac.post("/api/v1/sticker/upload", headers=_H,
                              json={"data_base64": ""})).status_code == 400


async def test_upload_bad_name(monkeypatch, fake_redis, tmp_path):
    """name 含路径分隔或 '..' → 400(白名单拒)"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    b64 = _b64(_PNG)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/sticker/upload", headers=_H,
                              json={"data_base64": b64, "name": "a/b.png"})).status_code == 400
        assert (await ac.post("/api/v1/sticker/upload", headers=_H,
                              json={"data_base64": b64, "name": ".."})).status_code == 400


async def test_upload_over_limit(monkeypatch, fake_redis, tmp_path):
    """超 5MB(6MB 字节)→ 400"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/upload", headers=_H,
                          json={"data_base64": _b64(b"x" * (6 * 1024 * 1024))})
        assert r.status_code == 400


# ================ delete ================

async def test_delete_roundtrip(monkeypatch, fake_redis, tmp_path):
    """上传后删除 → 200 + list 消失 + 物理文件删除;再删 → 404"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        j = (await ac.post("/api/v1/sticker/upload", headers=_H,
                           json={"data_base64": _b64(_PNG), "desc": "删我"})).json()
        fname = j["file"]
        assert (tmp_path / fname).exists()
        r = await ac.delete(f"/api/v1/sticker/{fname}", headers=_H)
        assert r.status_code == 200 and r.json() == {"deleted": fname}
        assert not (tmp_path / fname).exists()       # 物理删除
        items = (await ac.get("/api/v1/sticker/list", headers=_H)).json()["items"]
        assert items == []
        assert (await ac.delete(f"/api/v1/sticker/{fname}", headers=_H)).status_code == 404


async def test_delete_traversal_name(monkeypatch, fake_redis, tmp_path):
    """路径穿越样例('..' 编码 / 'a/b')→ 非 200(路由不匹配或白名单拒 → 404)"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r1 = await ac.delete("/api/v1/sticker/%2E%2E", headers=_H)      # URL 编码的 ".."
        assert r1.status_code in (400, 404)
        r2 = await ac.delete("/api/v1/sticker/a%2Fb", headers=_H)       # 编码的 "a/b"
        assert r2.status_code in (400, 404)


# ================ describe ================

async def test_describe_ok_updates_lib(monkeypatch, fake_redis, tmp_path):
    """vision 成功 → 200 且 lib 描述更新为新描述"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        j = (await ac.post("/api/v1/sticker/upload", headers=_H,
                           json={"data_base64": _b64(_PNG), "desc": "旧描述"})).json()
        fname = j["file"]

        async def fake_vision(data, ctype):
            return "[表情包: 新描述]"

        monkeypatch.setattr(ss, "_vision_token", fake_vision)
        r = await ac.post(f"/api/v1/sticker/{fname}/describe", headers=_H)
        assert r.status_code == 200
        assert r.json() == {"name": fname, "desc": "新描述"}
        assert await fake.hget("mychat:sticker:lib", fname) == "新描述"


async def test_describe_vision_fail_400(monkeypatch, fake_redis, tmp_path):
    """vision 返 None → 400;文件不存在同样 400"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    (tmp_path / "s.png").write_bytes(_PNG)

    async def fake_vision(data, ctype):
        return None

    monkeypatch.setattr(ss, "_vision_token", fake_vision)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/sticker/s.png/describe", headers=_H)).status_code == 400
        assert (await ac.post("/api/v1/sticker/nope.png/describe", headers=_H)).status_code == 400


# ================ render ================

async def test_render_ok(monkeypatch, fake_redis, tmp_path):
    """文字表情生成:200 + token= [表情包: 文字] + 文件落 tmp 库目录 + lib 已注册"""
    app, fake = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/render", headers=_H, json={"text": "摸鱼中"})
        assert r.status_code == 200
        j = r.json()
        assert j["token"] == "[表情包: 摸鱼中]" and j["desc"] == "摸鱼中"
        assert (tmp_path / j["file"]).exists()
        assert await fake.hget("mychat:sticker:lib", j["file"]) == "摸鱼中"
        # 生成后 list 可见(render 写 last_used)
        items = (await ac.get("/api/v1/sticker/list", headers=_H)).json()["items"]
        assert items and items[0]["last_used"]


async def test_render_blank_text_400(monkeypatch, fake_redis, tmp_path):
    """text 空白 → 400(render_text_sticker 抛 ValueError)"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        assert (await ac.post("/api/v1/sticker/render", headers=_H,
                              json={"text": "   "})).status_code == 400


# ================ 审查加固回归(2026-10-25) ================

async def test_upload_rejects_pre_decode_oversize(monkeypatch, fake_redis, tmp_path):
    """解码前 7MB 限长:8MB base64 字符串 → 400(防解码内存放大,与解码后 5MB 内容限双卡)"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/upload", headers=_H,
                          json={"data_base64": "A" * (8 * 1024 * 1024)})
        assert r.status_code == 400


async def test_upload_rejects_non_image_bytes(monkeypatch, fake_redis, tmp_path):
    """魔数校验:非图片二进制(即使带合法 desc)→ 400 且不落盘(防坏图入库破坏出站发送)"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/upload", headers=_H,
                          json={"data_base64": _b64(b"not-an-image-bytes!"), "desc": "假图"})
        assert r.status_code == 400
    assert not list(tmp_path.iterdir())


async def test_upload_rejects_invalid_desc(monkeypatch, fake_redis, tmp_path):
    """desc 超 40 字 → 400(违例描述配的 token 不被出站解析,QQ 会直出字面文本)"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/upload", headers=_H,
                          json={"data_base64": _b64(_PNG), "desc": "长" * 41})
        assert r.status_code == 400


async def test_upload_rejects_existing_name(monkeypatch, fake_redis, tmp_path):
    """显式 name 撞已有文件 → 400(拒绝静默覆盖造成"描述 A 实发图 B"错位,要替换先删)"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    (tmp_path / "dup.png").write_bytes(_PNG)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/upload", headers=_H,
                          json={"data_base64": _b64(_PNG), "name": "dup.png", "desc": "重复"})
        assert r.status_code == 400


async def test_render_template_whitelist(monkeypatch, fake_redis, tmp_path):
    """底图白名单:白名单外任意文件(如服务器任意路径)→ 回退纯色画布仍 200;
    库目录 templates/ 内底图正常使用——用确定性 md5 文件名区分两种路径"""
    import hashlib

    from PIL import Image

    def _expect_file(text: str, tpl_key: str) -> str:
        # 文件名 = render_{md5(文字|底图全路径)[:16]}.png;回退画布时 tpl_key 为空串
        ch = hashlib.md5(f"{text}|{tpl_key}".encode("utf-8")).hexdigest()[:16]
        return f"render_{ch}.png"

    outside = tmp_path / "secret.png"          # 白名单外(tmp_path 根,非 templates/ 子目录)
    outside.write_bytes(_PNG)
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/render", headers=_H,
                          json={"text": "白名单", "template": str(outside)})
        assert r.status_code == 200
        assert r.json()["file"] == _expect_file("白名单", "")   # 未采用白名单外底图

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        base = tpl_dir / "base.png"
        Image.new("RGB", (100, 100), (200, 30, 30)).save(base)  # PIL 造真 PNG 底图
        r2 = await ac.post("/api/v1/sticker/render", headers=_H,
                           json={"text": "白名单内", "template": str(base)})
        assert r2.status_code == 200
        assert r2.json()["file"] == _expect_file("白名单内", str(base.resolve()))  # 真用了底图


async def test_render_bad_font_size_400(monkeypatch, fake_redis, tmp_path):
    """font_size 非整数 → 400(防 int() 抛 TypeError 变 500)"""
    app, _ = _wire(monkeypatch, fake_redis, tmp_path)
    async with await _ac(app) as ac:
        r = await ac.post("/api/v1/sticker/render", headers=_H,
                          json={"text": "字号", "font_size": "abc"})
        assert r.status_code == 400
