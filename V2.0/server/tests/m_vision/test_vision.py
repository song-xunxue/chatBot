"""
M-vision 图像理解模块单测(2026-07-01)
覆盖:GLM vision provider(mock httpx)、stub、registry 降级、webhook 图片消息解析(含软失败)、
      parse_c2c_message attachments 解析、rest_multimodal 端点(鉴权+解析)。
mock httpx,全程不真调 GLM API。

作者: 李文煜
日期: 2026-07-01
"""
import base64
import json

import httpx
import pytest

from modality.base import VisionProvider
from modality.glm import GLMVisionProvider, _BASE as GLM_BASE
from modality.stub import StubVisionProvider
from modality.registry import get_vision
from core.config import settings


# —— httpx mock 工具(给 GLMVisionProvider 注入假 client)——
class _FakeResp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)   # type: ignore


class _FakeClient:
    """模拟 httpx.AsyncClient 上下文管理器:记录 post 请求,返预设响应"""
    def __init__(self, resp, captured=None):
        self._resp = resp
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, **kw):
        if self._captured is not None:
            self._captured["url"] = url
            self._captured["headers"] = headers
            self._captured["json"] = json
        return self._resp


# ================ GLM Vision Provider ================

@pytest.mark.asyncio
async def test_glm_vision_understand_returns_description(monkeypatch):
    """GLM vision understand:mock 200 响应 → 返回描述文本"""
    resp = _FakeResp({"choices": [{"message": {"content": "一只橘猫趴在键盘上"}}]})
    captured: dict = {}
    monkeypatch.setattr("modality.glm.httpx.AsyncClient",
                        lambda **kw: _FakeClient(resp, captured))
    p = GLMVisionProvider(api_key="k", model="glm-4v-flash")
    desc = await p.understand(b"\x89PNG fake", "描述图片", mime="image/png")
    assert desc == "一只橘猫趴在键盘上"
    # 验证请求:打到 GLM endpoint + 正确 model + 图片 base64 进 payload
    assert captured["url"] == f"{GLM_BASE}/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer k"
    msg = captured["json"]["messages"][0]["content"]
    assert any(c["type"] == "image_url" for c in msg)
    img_url = [c for c in msg if c["type"] == "image_url"][0]["image_url"]["url"]
    assert img_url.startswith("data:image/png;base64,")
    assert base64.b64decode(img_url.split(",", 1)[1]) == b"\x89PNG fake"


@pytest.mark.asyncio
async def test_glm_vision_uses_settings_model_and_key(monkeypatch):
    """无显式 api_key/model 时,用 settings.glm_api_key + settings.glm_vision_model"""
    monkeypatch.setattr(settings, "glm_api_key", "set-key")
    monkeypatch.setattr(settings, "glm_vision_model", "glm-4v-plus")
    resp = _FakeResp({"choices": [{"message": {"content": "图"}}]})
    captured: dict = {}
    monkeypatch.setattr("modality.glm.httpx.AsyncClient",
                        lambda **kw: _FakeClient(resp, captured))
    p = GLMVisionProvider()   # 不传参 → 走 settings
    await p.understand(b"x", "p")
    assert captured["json"]["model"] == "glm-4v-plus"
    assert captured["headers"]["Authorization"] == "Bearer set-key"


# ================ Stub ================

@pytest.mark.asyncio
async def test_stub_vision_returns_placeholder():
    """stub provider 不调 API,返固定占位"""
    s = StubVisionProvider()
    out = await s.understand(b"img", "p")
    assert "stub" in out


# ================ Registry 降级 ================

def test_get_vision_glm_with_key(monkeypatch):
    """glm + 有 key → GLMVisionProvider"""
    monkeypatch.setattr(settings, "multimodal_vision_provider", "glm")
    monkeypatch.setattr(settings, "glm_api_key", "k")
    assert isinstance(get_vision(), GLMVisionProvider)


def test_get_vision_glm_no_key_degrades_to_stub(monkeypatch):
    """glm + 无 key → 降级 Stub(链路不断)"""
    monkeypatch.setattr(settings, "multimodal_vision_provider", "glm")
    monkeypatch.setattr(settings, "glm_api_key", "")
    assert isinstance(get_vision(), StubVisionProvider)


def test_get_vision_unknown_provider_degrades_to_stub(monkeypatch):
    """未知名 → Stub"""
    monkeypatch.setattr(settings, "multimodal_vision_provider", "xxx")
    monkeypatch.setattr(settings, "glm_api_key", "k")
    assert isinstance(get_vision(), StubVisionProvider)


def test_get_vision_stub_explicit(monkeypatch):
    monkeypatch.setattr(settings, "multimodal_vision_provider", "stub")
    assert isinstance(get_vision(), StubVisionProvider)


# ================ parse_c2c_message attachments ================

def test_parse_c2c_message_captures_attachments():
    """图片消息:attachments 从 d 解析进 C2CMessage"""
    from qq.webhook import parse_c2c_message
    d = {"author": {"user_openid": "OID"}, "content": "", "id": "M",
         "attachments": [{"content_type": "image/png", "url": "https://qq/img/1"}]}
    msg = parse_c2c_message(d)
    assert msg.openid == "OID"
    assert msg.attachments == [{"content_type": "image/png", "url": "https://qq/img/1"}]


def test_parse_c2c_message_no_attachments_defaults_empty():
    """纯文本消息:attachments 默认空 list"""
    from qq.webhook import parse_c2c_message
    msg = parse_c2c_message({"author": {"user_openid": "O"}, "content": "hi", "id": "M"})
    assert msg.attachments == []


# ================ webhook _resolve_msg_text(图片解析 + 软失败)=================

@pytest.mark.asyncio
async def test_resolve_msg_text_text_only():
    """纯文本消息 → 直接返文本"""
    from qq.webhook import _resolve_msg_text
    from qq.types import C2CMessage
    msg = C2CMessage(openid="O", content="你好", msg_id="M", timestamp="", raw={}, attachments=[])
    assert await _resolve_msg_text(msg) == "你好"


@pytest.mark.asyncio
async def test_resolve_msg_text_image_success(monkeypatch):
    """图片消息 + vision 成功 → 文本含 [用户发了一张图片: desc]"""
    from qq import webhook
    from qq.types import C2CMessage
    async def fake_desc(att):
        return "一只猫"
    monkeypatch.setattr(webhook, "_describe_image", fake_desc)
    msg = C2CMessage(openid="O", content="", msg_id="M", timestamp="", raw={},
                     attachments=[{"content_type": "image/png", "url": "u"}])
    out = await webhook._resolve_msg_text(msg)
    assert "[用户发了一张图片: 一只猫]" in out


@pytest.mark.asyncio
async def test_resolve_msg_text_image_softfail(monkeypatch):
    """图片消息 + vision 失败(返空)→ 文本含 [用户发了一张图片,但解析失败](软失败不抛)"""
    from qq import webhook
    from qq.types import C2CMessage
    async def fake_desc(att):
        return ""
    monkeypatch.setattr(webhook, "_describe_image", fake_desc)
    msg = C2CMessage(openid="O", content="", msg_id="M", timestamp="", raw={},
                     attachments=[{"content_type": "image/jpeg", "url": "u"}])
    out = await webhook._resolve_msg_text(msg)
    assert "[用户发了一张图片,但解析失败]" in out


@pytest.mark.asyncio
async def test_resolve_msg_text_vision_disabled(monkeypatch):
    """multimodal_vision_enable=False → 图片附件不解析(只当文本)"""
    from qq import webhook
    from qq.types import C2CMessage
    monkeypatch.setattr(settings, "multimodal_vision_enable", False)
    async def boom(att):  # 不应被调用
        raise RuntimeError("不应到这")
    monkeypatch.setattr(webhook, "_describe_image", boom)
    msg = C2CMessage(openid="O", content="看图", msg_id="M", timestamp="", raw={},
                     attachments=[{"content_type": "image/png", "url": "u"}])
    assert await webhook._resolve_msg_text(msg) == "看图"


@pytest.mark.asyncio
async def test_describe_image_softfail_on_download_error(monkeypatch):
    """_describe_image 下载失败 → 返空串(不抛),全程软失败"""
    from qq import webhook
    async def boom(url):
        raise httpx.ConnectError("nope")
    monkeypatch.setattr(webhook, "send_download", boom)
    out = await webhook._describe_image({"url": "https://qq/x", "content_type": "image/png"})
    assert out == ""


# ================ REST /multimodal/vision ================

def test_rest_vision_describe_returns_description(monkeypatch, fake_redis):
    """POST /multimodal/vision 上传图 → {description}(vision mocked)"""
    from fastapi.testclient import TestClient
    from main import app
    async def fake_understand(self, img, prompt, mime="image/jpeg"):
        return "一只狗"
    monkeypatch.setattr(GLMVisionProvider, "understand", fake_understand)
    monkeypatch.setattr(settings, "glm_api_key", "k")   # 让 get_vision 返 GLM 而非 stub
    with TestClient(app) as c:
        r = c.post("/api/v1/multimodal/vision",
                   headers={"X-Access-Token": settings.access_token},
                   files={"file": ("a.png", b"\x89PNG", "image/png")})
    assert r.status_code == 200
    assert r.json()["description"] == "一只狗"


def test_rest_vision_requires_auth(fake_redis):
    """无 token → 401"""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        r = c.post("/api/v1/multimodal/vision",
                   files={"file": ("a.png", b"\x89PNG", "image/png")})
    assert r.status_code == 401


def test_rest_vision_softfail_on_error(monkeypatch, fake_redis):
    """vision 抛错 → 200 + {description:"", error:...}(软失败不 500)"""
    from fastapi.testclient import TestClient
    from main import app
    async def boom(self, img, prompt, mime="image/jpeg"):
        raise RuntimeError("GLM 429")
    monkeypatch.setattr(GLMVisionProvider, "understand", boom)
    monkeypatch.setattr(settings, "glm_api_key", "k")
    with TestClient(app) as c:
        r = c.post("/api/v1/multimodal/vision",
                   headers={"X-Access-Token": settings.access_token},
                   files={"file": ("a.png", b"\x89PNG", "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["description"] == ""
    assert "error" in body
