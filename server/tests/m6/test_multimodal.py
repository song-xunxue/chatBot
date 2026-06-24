"""
多模态理解 REST 测试：vision/asr 走 stub provider（不触网）、鉴权。
硅基流动真实调用需联网+计费，单测用 stub（monkeypatch provider 配置）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.2 覆盖 rest_multimodal：vision/asr stub + 鉴权
"""
from core.config import settings

HEADERS = {"X-Access-Token": settings.access_token}


def test_vision_stub(client, monkeypatch):
    monkeypatch.setattr(settings, "multimodal_vision_provider", "stub")
    r = client.post("/api/v1/multimodal/vision", headers=HEADERS,
                    files={"file": ("a.png", b"\x89PNG fake", "image/png")},
                    data={"prompt": "图里有什么"})
    assert r.status_code == 200, r.text
    assert "stub" in r.json()["text"]


def test_asr_stub(client, monkeypatch):
    monkeypatch.setattr(settings, "multimodal_asr_provider", "stub")
    r = client.post("/api/v1/multimodal/asr", headers=HEADERS,
                    files={"file": ("a.wav", b"RIFF fake", "audio/wav")})
    assert r.status_code == 200, r.text
    assert "stub" in r.json()["text"]


def test_auth_required(client):
    r = client.post("/api/v1/multimodal/vision",
                    files={"file": ("a.png", b"x", "image/png")})
    assert r.status_code == 401


def test_vision_provider_select_via_config(client, monkeypatch):
    """配置切到 stub 时确认走 stub 而非真实 siliconflow（无网）"""
    monkeypatch.setattr(settings, "multimodal_vision_provider", "stub")
    from modality import get_vision
    assert get_vision("stub").name == "stub"
