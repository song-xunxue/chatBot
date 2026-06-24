"""
人设 REST 接口测试（TestClient + fakeredis）
验证 CRUD / 导入 / 导出 / 绑定 / 鉴权

作者: 李文煜
日期: 2026-06-23

2026-06-23
变更说明：
  1. M3.1 覆盖 rest_persona 全部端点
"""
import json

from core.config import settings

HEADERS = {"X-Access-Token": settings.access_token}


def test_create_get_update_delete(client):
    r = client.post("/api/v1/persona",
                    json={"name": "测试人设", "description": "D", "creator_notes": "C"},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    # get
    assert client.get(f"/api/v1/persona/{pid}", headers=HEADERS).json()["name"] == "测试人设"
    # update
    client.put(f"/api/v1/persona/{pid}", json={"name": "改名"}, headers=HEADERS)
    assert client.get(f"/api/v1/persona/{pid}", headers=HEADERS).json()["name"] == "改名"
    # delete
    assert client.delete(f"/api/v1/persona/{pid}", headers=HEADERS).json()["deleted"] is True
    assert client.get(f"/api/v1/persona/{pid}", headers=HEADERS).status_code == 404


def test_list_contains_default(client):
    # lifespan 已 seed default
    r = client.get("/api/v1/persona", headers=HEADERS)
    ids = [p["id"] for p in r.json()]
    assert "default" in ids


def test_import_nested(client):
    raw = {"data": {"prompts": {"abc": {"data": {"name": "导入", "description": "D"}}}}}
    r = client.post("/api/v1/persona/import",
                    files={"file": ("p.json", json.dumps(raw).encode(), "application/json")},
                    headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "abc"
    assert r.json()["name"] == "导入"


def test_export_default(client):
    r = client.get("/api/v1/persona/default/export", headers=HEADERS)
    assert r.status_code == 200
    assert "default" in r.json()["data"]["prompts"]


def test_auth_required_without_token(client):
    assert client.get("/api/v1/persona").status_code == 401


def test_bind_object(client):
    r = client.post("/api/v1/persona/default/bind/obj1", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["persona_id"] == "default"


def test_upload_avatar(client):
    r = client.post("/api/v1/persona/default/avatar",
                    files={"file": ("a.png", b"\x89PNG fake", "image/png")},
                    headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["avatar"].endswith(".png")
