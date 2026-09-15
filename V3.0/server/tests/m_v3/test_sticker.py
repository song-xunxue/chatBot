"""
表情包收发单测(2026-09-15):
1. sticker_store:token 拆分/解析、ingest(下载 mock+vision mock+mface summary 短路+缓存)、
   find_sticker 匹配、register_existing
2. adapter/onebot send_text:token → image 段(base64)、未匹配保留字面、纯文本不受影响
3. 批注:chat_store.set_note + REST PATCH /chat/messages/{mid}/note(含 user 消息)

作者: 李文煜
日期: 2026-09-15
"""
import base64
import json

import httpx
import pytest
from fastapi import FastAPI

import storage.redis_client as redis_client
import storage.sticker_store as ss
from core.config import settings

_H = {"X-Access-Token": "t-token"}


# ================ token 工具 ================

def test_split_reply_with_tokens():
    """回复拆分:文本 run + sticker token 交替;无 token 整段文本"""
    out = ss.split_reply_with_tokens("哈哈\n[表情包: 猫猫点头]\n好呀~")
    assert out == [("text", "哈哈\n"), ("sticker", "猫猫点头"), ("text", "\n好呀~")]
    assert ss.split_reply_with_tokens("纯文本") == [("text", "纯文本")]
    # 全角冒号与首尾空白容错
    assert ss.split_reply_with_tokens("[表情包： 开心]") == [("sticker", "开心")]


def test_parse_token():
    """vision 输出解析:标准格式/容错格式/垃圾输出 None"""
    assert ss._parse_token("[表情包: 猫猫开心点头]") == ("表情包", "猫猫开心点头")
    assert ss._parse_token("[图片: 自拍]") == ("图片", "自拍")
    assert ss._parse_token("『表情包: 摸鱼』") == ("表情包", "摸鱼")
    assert ss._parse_token("这是一个猫") is None


# ================ ingest ================

def _fake_img(content=b"GIF89a-fake", ctype="image/gif"):
    """构造 (bytes, content_type) 元组,对齐 sticker_store._download 的返回契约"""
    return content, ctype


async def test_ingest_sticker_saves_and_caches(monkeypatch, fake_redis, tmp_path):
    """ingest:下载+vision 描述 → 存文件+注册库+缓存;二次调用命中缓存不再下载"""
    monkeypatch.setattr(ss, "STICKER_DIR", tmp_path)

    calls = {"download": 0, "vision": 0}

    async def fake_dl(url):
        calls["download"] += 1
        return _fake_img()

    async def fake_vision(data, ctype):
        calls["vision"] += 1
        return "[表情包: 猫猫摸鱼]"

    monkeypatch.setattr(ss, "_download", fake_dl)
    monkeypatch.setattr(ss, "_vision_token", fake_vision)

    t1 = await ss.ingest(fake_redis, "https://img.qq/a.gif")
    assert t1 == "[表情包: 猫猫摸鱼]"
    files = list(tmp_path.iterdir())
    assert len(files) == 1 and files[0].suffix == ".gif"
    lib = await fake_redis.hgetall("mychat:sticker:lib")
    assert lib[files[0].name] == "猫猫摸鱼"

    # 同内容再发(url 不同):缓存按内容 md5——下载仍执行(签名 url 无法免下),vision 只一次
    t2 = await ss.ingest(fake_redis, "https://img.qq/other-signed-url.gif")
    assert t2 == t1 and calls["download"] == 2 and calls["vision"] == 1


async def test_ingest_mface_summary_shortcut(monkeypatch, fake_redis, tmp_path):
    """mface 自带 summary → 免 vision 直接采用;summary 空走 vision"""
    monkeypatch.setattr(ss, "STICKER_DIR", tmp_path)

    async def fake_dl(url):
        # 不同 url 不同字节(同字节会因内容 md5 相同而命中缓存——那是另一个测试的断言点)
        return _fake_img(content=f"GIF89a-{url[-6:]}".encode())

    vision_calls = []

    async def fake_vision(data, ctype):
        vision_calls.append(1)
        return "[表情包: 兜底]"

    monkeypatch.setattr(ss, "_download", fake_dl)
    monkeypatch.setattr(ss, "_vision_token", fake_vision)

    t = await ss.ingest(fake_redis, "https://img.qq/m.gif", summary="[开心到转圈]")
    assert t == "[表情包: 开心到转圈]" and not vision_calls

    t2 = await ss.ingest(fake_redis, "https://img.qq/m2.gif", summary="")
    assert t2 == "[表情包: 兜底]" and len(vision_calls) == 1


async def test_ingest_photo_not_saved(monkeypatch, fake_redis, tmp_path):
    """真实照片:token [图片: ...] 但不入库不占磁盘"""
    monkeypatch.setattr(ss, "STICKER_DIR", tmp_path)

    async def fake_dl(url):
        return _fake_img(content=b"\xff\xd8fakejpg", ctype="image/jpeg")

    async def fake_vision(data, ctype):
        return "[图片: 宿舍自拍]"

    monkeypatch.setattr(ss, "_download", fake_dl)
    monkeypatch.setattr(ss, "_vision_token", fake_vision)
    t = await ss.ingest(fake_redis, "https://img.qq/p.jpg")
    assert t == "[图片: 宿舍自拍]"
    assert not list(tmp_path.iterdir())
    assert not await fake_redis.hgetall("mychat:sticker:lib")


async def test_ingest_soft_fail_placeholder(monkeypatch, fake_redis, tmp_path):
    """下载失败 → [图片] 回退(链路不断);vision 失败同样回退"""
    monkeypatch.setattr(ss, "STICKER_DIR", tmp_path)

    async def fail_dl(url):
        return None

    monkeypatch.setattr(ss, "_download", fail_dl)
    assert await ss.ingest(fake_redis, "https://img.qq/dead.gif") == "[图片]"


# ================ find_sticker / register_existing ================

async def test_find_sticker_match(fake_redis, tmp_path):
    """双向子串匹配(忽略大小写);无匹配/文件缺失返 None"""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(ss, "STICKER_DIR", tmp_path)
    try:
        f = tmp_path / "abc.gif"
        f.write_bytes(b"GIF89a")
        await fake_redis.hset("mychat:sticker:lib", "abc.gif", "猫猫开心点头")
        assert (await ss.find_sticker(fake_redis, "猫猫")) == f      # 库描述含查询
        assert (await ss.find_sticker(fake_redis, "猫猫开心点头哈哈哈")) == f  # 查询含库描述
        assert await ss.find_sticker(fake_redis, "狗狗") is None
        await fake_redis.hset("mychat:sticker:lib", "ghost.gif", "幽灵")
        assert await ss.find_sticker(fake_redis, "幽灵") is None     # 文件不存在
    finally:
        monkeypatch.undo()


async def test_register_existing(monkeypatch, fake_redis, tmp_path):
    """目录内未注册文件补描述注册;照片不注册;已注册跳过"""
    monkeypatch.setattr(ss, "STICKER_DIR", tmp_path)
    (tmp_path / "s1.gif").write_bytes(b"GIF89a-1")
    (tmp_path / "p2.jpg").write_bytes(b"\xff\xd8jpg")

    async def fake_vision(data, ctype):
        return "[表情包: 小猫打滚]" if data.startswith(b"GIF") else "[图片: 风景照]"

    monkeypatch.setattr(ss, "_vision_token", fake_vision)
    r = await ss.register_existing(fake_redis)
    assert r["registered"] == 1 and r["skipped"] == 1
    lib = await fake_redis.hgetall("mychat:sticker:lib")
    assert lib == {"s1.gif": "小猫打滚"}
    # 幂等:再跑全部跳过
    r2 = await ss.register_existing(fake_redis)
    assert r2["registered"] == 0 and r2["skipped"] == 2


# ================ adapter send_text token 翻译 ================

async def test_adapter_send_text_sticker_segments(monkeypatch, fake_redis, tmp_path):
    """send_text:表情包独立成条——文本一条 + 每个表情包各一条(分开 send);
    未匹配 token 保留字面文本;纯文本单条零影响"""
    from adapter import onebot as ob
    from adapter.onebot import OnebotAdapter

    f = tmp_path / "cat.gif"
    f.write_bytes(b"GIF89aCAT")
    await fake_redis.hset("mychat:sticker:lib", "cat.gif", "猫猫开心点头")
    monkeypatch.setattr(ss, "STICKER_DIR", tmp_path)
    monkeypatch.setattr(ob.random, "uniform", lambda a, b: 0)   # 免去条间延迟

    sent: list[dict] = []

    async def fake_call(action, params, timeout=None):
        sent.append(params)
        return {"status": "ok", "data": {"message_id": 1}}

    import onebot.ws_client as wsc
    monkeypatch.setattr(wsc, "call_action", fake_call)
    monkeypatch.setattr(redis_client, "_redis", fake_redis)

    ad = OnebotAdapter()
    # 文本+匹配 token → 两条独立消息:文本条 + 表情包条(不混发)
    await ad.send_text("111", "哈哈\n[表情包: 猫猫开心点头]")
    assert len(sent) == 2
    assert sent[0]["message"] == [{"type": "text", "data": {"text": "哈哈"}}]
    assert sent[1]["message"][0]["type"] == "image"
    assert base64.b64decode(
        sent[1]["message"][0]["data"]["file"].replace("base64://", "")) == b"GIF89aCAT"
    # token 前后都有文本 → 三条:前文本/表情/后文本(边界换行剥掉)
    del sent[:]
    await ad.send_text("111", "哈哈\n[表情包: 猫猫开心点头]\n好呀~")
    assert [m["message"][0]["data"].get("text") or "image" for m in sent] == ["哈哈", "image", "好呀~"]
    # 未匹配 token:保留字面(透明可排查),单条
    del sent[:]
    await ad.send_text("111", "[表情包: 不存在的狗]")
    assert sent[0]["message"] == [{"type": "text", "data": {"text": "[表情包: 不存在的狗]"}}]
    # 纯文本零影响
    del sent[:]
    await ad.send_text("111", "普通回复~")
    assert sent[0]["message"] == [{"type": "text", "data": {"text": "普通回复~"}}]


# ================ 批注 ================

async def test_set_note_and_rest_endpoint(monkeypatch, fake_redis):
    """批注:chat_store.set_note 任意 sender(含 user)+ REST PATCH 端点(404/成功/清空)"""
    from storage import chat_store
    from api.rest_chat import router as chat_router

    mid = await chat_store.append_message(fake_redis, "10001", sender="user", content="夫君你可真行")
    # chat_store 层
    assert await chat_store.set_note(fake_redis, mid, "这句是撒娇不是夸奖") == "这句是撒娇不是夸奖"
    assert (await chat_store.get_message(fake_redis, mid))["score_note"] == "这句是撒娇不是夸奖"
    assert await chat_store.set_note(fake_redis, "no-such-mid", "x") is None

    # REST 层
    monkeypatch.setattr(redis_client, "_redis", fake_redis)
    monkeypatch.setattr(settings, "access_token", "t-token")
    app = FastAPI()
    app.include_router(chat_router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        assert (await ac.patch("/api/v1/chat/messages/no-such/note", headers=_H,
                               json={"note": "x"})).status_code == 404
        r = await ac.patch(f"/api/v1/chat/messages/{mid}/note", headers=_H,
                           json={"note": "评分理由:撒娇语气分高;暗含:求哄"})
        assert r.status_code == 200 and r.json()["note"].startswith("评分理由")
        # 清空
        r2 = await ac.patch(f"/api/v1/chat/messages/{mid}/note", headers=_H, json={"note": ""})
        assert r2.status_code == 200 and r2.json()["note"] == ""


async def test_reverse_infer_note_embedded(fake_redis):
    """反推样本带 score_note 时 prompt 附 [批注: ...];无 note 不附"""
    from score import reverse_infer as ri

    class _FakeLLM:
        async def chat(self, messages, model="", **opts):
            # 捕获 prompt 供断言
            test_reverse_infer_note_embedded.prompt = messages[0].content
            from llm.base import LLMResponse
            return LLMResponse(text="{}")

    mid = "noteembed01"
    await fake_redis.hset(f"mychat:msg:{mid}", "score_note", "这句其实是撒娇")
    await fake_redis.hset("mychat:msg:plain01", "score_note", "")

    samples = [{"text": "夫君你可真行", "source": "dialog", "mid": mid},
               {"text": "普通回复", "source": "dialog", "mid": "plain01"}]
    await ri._llm_extract(samples, [], _FakeLLM(), redis=fake_redis)
    p = test_reverse_infer_note_embedded.prompt
    assert "[真实对话] 夫君你可真行 [批注: 这句其实是撒娇]" in p
    assert "[真实对话] 普通回复" in p and "普通回复 [批注" not in p
    # redis 缺省(旧调用方):不炸;样本行不带批注(prompt 模板自身的 [批注] 教学文字除外)
    test_reverse_infer_note_embedded.prompt = ""
    await ri._llm_extract(samples, [], _FakeLLM())
    p2 = test_reverse_infer_note_embedded.prompt
    assert "夫君你可真行 [批注" not in p2 and "普通回复 [批注" not in p2
