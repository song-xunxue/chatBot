"""
RestClient mock 测试：验证 vision / asr / get_pet_avatar_bytes / get / post 的 httpx
调用（URL/header/参数）。回填 M5/M6 测试缺口——之前只冒烟、未 mock 网络层。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. 回填：mock httpx 覆盖 RestClient 全部方法
"""
import httpx
import pytest
from net.rest_client import RestClient


class _Resp:
    """假 httpx 响应"""
    def __init__(self, status=200, json_data=None, content=b"", ctype="application/json"):
        self.status_code = status
        self._json = json_data if json_data is not None else {}
        self.content = content
        self.headers = {"content-type": ctype}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)


@pytest.fixture
def rc():
    return RestClient("http://x:8000", "tok")


def test_get_injects_token(monkeypatch, rc):
    cap = {}

    def fake_get(url, **kwargs):
        cap["url"] = url
        cap["headers"] = kwargs.get("headers")
        return _Resp(json_data=[{"id": "a"}])

    monkeypatch.setattr(httpx, "get", fake_get)
    assert rc.get("/api/v1/persona") == [{"id": "a"}]
    assert cap["headers"]["X-Access-Token"] == "tok"
    assert cap["url"] == "http://x:8000/api/v1/persona"


def test_post(monkeypatch, rc):
    cap = {}

    def fake_post(url, **kwargs):
        cap["url"] = url
        cap["json"] = kwargs.get("json")
        return _Resp(json_data={"ok": 1})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert rc.post("/p", json_body={"a": 1}) == {"ok": 1}
    assert cap["json"] == {"a": 1}


def test_get_pet_avatar_bytes_ok(monkeypatch, rc):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(content=b"\x89PNG", ctype="image/png"))
    assert rc.get_pet_avatar_bytes() == b"\x89PNG"


def test_get_pet_avatar_bytes_404_returns_none(monkeypatch, rc):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(status=404))
    assert rc.get_pet_avatar_bytes() is None


def test_vision(monkeypatch, rc):
    cap = {}

    def fake_post(url, **kwargs):
        cap["data"] = kwargs.get("data")
        cap["files"] = kwargs.get("files")
        return _Resp(json_data={"text": "一只猫"})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert rc.vision(b"imgbytes", prompt="描述", mime="image/png") == "一只猫"
    assert cap["data"]["prompt"] == "描述"
    assert cap["files"] is not None


def test_asr(monkeypatch, rc):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(json_data={"text": "你好"}))
    assert rc.asr(b"audio", fmt="wav") == "你好"
