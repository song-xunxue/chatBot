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


# V1.1 M9：PUT 改 PATCH 深度合并（修 V1.0 丢字段 + created_ts 重置 bug）
def test_put_preserves_other_fields(client):
    r = client.post("/api/v1/persona",
                    json={"name": "原", "description": "D", "creator_notes": "C",
                          "profile": {"age": "18", "gender": "女"}},
                    headers=HEADERS)
    pid = r.json()["id"]
    client.put(f"/api/v1/persona/{pid}", json={"name": "改名"}, headers=HEADERS)
    got = client.get(f"/api/v1/persona/{pid}", headers=HEADERS).json()
    assert got["name"] == "改名"
    assert got["description"] == "D"        # 未丢
    assert got["creator_notes"] == "C"      # 未丢
    assert got["profile"]["age"] == "18"    # 嵌套未丢
    assert got["profile"]["gender"] == "女"


def test_put_deep_merge_nested(client):
    r = client.post("/api/v1/persona",
                    json={"name": "X", "profile": {"age": "18", "gender": "女"}},
                    headers=HEADERS)
    pid = r.json()["id"]
    # PUT 只改 profile.gender，age 应保留（深度合并而非整体替换）
    client.put(f"/api/v1/persona/{pid}", json={"profile": {"gender": "男"}}, headers=HEADERS)
    got = client.get(f"/api/v1/persona/{pid}", headers=HEADERS).json()
    assert got["profile"]["gender"] == "男"
    assert got["profile"]["age"] == "18"


def test_put_preserves_created_ts(client):
    r = client.post("/api/v1/persona", json={"name": "T"}, headers=HEADERS)
    pid = r.json()["id"]
    created = r.json()["created_ts"]
    client.put(f"/api/v1/persona/{pid}", json={"name": "T2"}, headers=HEADERS)
    got = client.get(f"/api/v1/persona/{pid}", headers=HEADERS).json()
    assert got["created_ts"] == created   # V1.0 bug 修复：不重置


def test_history_and_rollback_endpoints(client):
    pid = client.post("/api/v1/persona", json={"name": "H"}, headers=HEADERS).json()["id"]
    h = client.get(f"/api/v1/persona/{pid}/history", headers=HEADERS).json()
    assert h["history"] == []
    r = client.post(f"/api/v1/persona/{pid}/rollback", json={"version_no": 1}, headers=HEADERS)
    assert r.status_code == 404   # 无快照，回滚 404
