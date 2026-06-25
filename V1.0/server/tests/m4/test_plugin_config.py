"""
插件配置 REST 测试（复用顶层 client 夹具；lifespan 会 init_plugins 加载真实 hello）
覆盖：列表/详情/enable/disable/按对象配置 GET+PUT/鉴权/404。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M4.2 覆盖 rest_plugin 全部端点
"""
from core.config import settings

HEADERS = {"X-Access-Token": settings.access_token}


def test_list_plugins_includes_hello(client):
    r = client.get("/api/v1/plugin", headers=HEADERS)
    assert r.status_code == 200, r.text
    names = [p["name"] for p in r.json()]
    assert "hello" in names


def test_get_plugin_detail(client):
    r = client.get("/api/v1/plugin/hello", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "hello"
    assert any(h["name"] == "on_after_llm" for h in body["hooks"])


def test_enable_then_disable(client):
    r = client.post("/api/v1/plugin/hello/enable", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["global_enabled"] is True
    assert client.get("/api/v1/plugin/hello", headers=HEADERS).json()["global_enabled"] is True
    r = client.post("/api/v1/plugin/hello/disable", headers=HEADERS)
    assert r.json()["global_enabled"] is False


def test_object_config_put_and_get(client):
    client.post("/api/v1/plugin/hello/enable", headers=HEADERS)
    r = client.put("/api/v1/plugin/object/o1/hello", headers=HEADERS,
                   json={"enabled": True, "params": {"suffix": "[X]"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["params"]["suffix"] == "[X]"
    # GET 反映
    r = client.get("/api/v1/plugin/object/o1", headers=HEADERS)
    cfg = next(p for p in r.json() if p["name"] == "hello")
    assert cfg["enabled"] is True
    assert cfg["params"]["suffix"] == "[X]"
    assert cfg["explicit"] is True


def test_object_config_disable_override(client):
    """全局开 + 按对象关 → 该对象不启用"""
    client.post("/api/v1/plugin/hello/enable", headers=HEADERS)
    client.put("/api/v1/plugin/object/o1/hello", headers=HEADERS, json={"enabled": False})
    r = client.get("/api/v1/plugin/object/o1", headers=HEADERS)
    cfg = next(p for p in r.json() if p["name"] == "hello")
    assert cfg["enabled"] is False


def test_auth_required_without_token(client):
    assert client.get("/api/v1/plugin").status_code == 401


def test_plugin_not_found(client):
    assert client.post("/api/v1/plugin/nope/enable", headers=HEADERS).status_code == 404


def test_reload(client):
    r = client.post("/api/v1/plugin/hello/reload", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["reloaded"] is True


def test_object_config_rejects_non_dict_params(client):
    """params 非 dict → 400（防 get_params 损坏导致插件静默失效）"""
    client.post("/api/v1/plugin/hello/enable", headers=HEADERS)
    r = client.put("/api/v1/plugin/object/o1/hello", headers=HEADERS,
                   json={"params": "not-a-dict"})
    assert r.status_code == 400
