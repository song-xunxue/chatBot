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


# (V3.0 精简:webhook parse/resolve 测试段已随官方栈删除;vision provider 测试保留;onebot 入站图片在 m_v3)
