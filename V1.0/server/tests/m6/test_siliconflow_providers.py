"""
硅基流动 Vision/ASR Provider mock 测试：验证请求 URL/鉴权/payload 构造 + 响应解析。
回填 M6.2 缺口（之前只测 stub 路径，未 mock 真实 provider 的 httpx 调用）。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. 回填：mock httpx.AsyncClient 覆盖 SiliconFlowVision/ASR Provider
"""
import pytest
import modality.siliconflow as sf


class _FakeResp:
    def __init__(self, json_data):
        self._j = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._j


class _FakeClient:
    """假 httpx.AsyncClient：按 URL 返回不同响应，并记录请求参数"""
    def __init__(self, *a, **k):
        self.last = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, files=None, data=None):
        self.last = {"url": url, "headers": headers, "json": json, "files": files, "data": data}
        if "chat/completions" in url:
            return _FakeResp({"choices": [{"message": {"content": "图里是一只猫"}}]})
        return _FakeResp({"text": "你好世界"})


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(sf.httpx, "AsyncClient", lambda *a, **k: client)
    return client


async def test_vision_understand(fake_client):
    p = sf.SiliconFlowVisionProvider(api_key="k")
    text = await p.understand(b"imgbytes", prompt="描述这张图", mime="image/png")
    assert text == "图里是一只猫"
    assert "chat/completions" in fake_client.last["url"]
    assert fake_client.last["headers"]["Authorization"] == "Bearer k"
    # 多模态 payload：content 含 image_url
    content = fake_client.last["json"]["messages"][0]["content"]
    assert any(c["type"] == "image_url" for c in content)
    assert any(c["type"] == "text" and "描述" in c["text"] for c in content)


async def test_asr_transcribe(fake_client):
    p = sf.SiliconFlowASRProvider(api_key="k2")
    text = await p.transcribe(b"audiobytes", fmt="wav")
    assert text == "你好世界"
    assert "audio/transcriptions" in fake_client.last["url"]
    assert fake_client.last["headers"]["Authorization"] == "Bearer k2"
    assert fake_client.last["data"]["model"]          # 带模型名
    assert fake_client.last["files"] is not None      # 上传了音频文件
