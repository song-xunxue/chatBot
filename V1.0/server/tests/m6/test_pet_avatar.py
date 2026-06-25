"""
桌宠头像 REST 测试：上传/获取/删除、格式限制、鉴权。
复用顶层 client 夹具(fakeredis + lifespan)；monkeypatch _PET_DIR 到临时目录防污染。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.1 覆盖 rest_pet：upload/get/delete/bad_ext/auth
"""
from core.config import settings

HEADERS = {"X-Access-Token": settings.access_token}


def test_upload_get_delete(client, monkeypatch, tmp_path):
    import api.rest_pet as rp
    monkeypatch.setattr(rp, "_PET_DIR", tmp_path / "pet")
    # 上传
    r = client.post("/api/v1/pet/avatar", headers=HEADERS,
                    files={"file": ("fox.png", b"\x89PNG fake", "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["avatar"].endswith("avatar.png")
    # 获取
    r = client.get("/api/v1/pet/avatar", headers=HEADERS)
    assert r.status_code == 200
    assert r.content == b"\x89PNG fake"
    # 删除
    r = client.delete("/api/v1/pet/avatar", headers=HEADERS)
    assert r.json()["deleted"] is True
    # 删除后 404
    assert client.get("/api/v1/pet/avatar", headers=HEADERS).status_code == 404


def test_upload_replaces_old(client, monkeypatch, tmp_path):
    """再次上传不同扩展名：旧文件被清理，只保留新的"""
    import api.rest_pet as rp
    monkeypatch.setattr(rp, "_PET_DIR", tmp_path / "pet")
    client.post("/api/v1/pet/avatar", headers=HEADERS,
                files={"file": ("a.png", b"PNG", "image/png")})
    client.post("/api/v1/pet/avatar", headers=HEADERS,
                files={"file": ("b.jpg", b"JPG", "image/jpeg")})
    assert not (tmp_path / "pet" / "avatar.png").exists()
    assert (tmp_path / "pet" / "avatar.jpg").is_file()


def test_reject_bad_extension(client, monkeypatch, tmp_path):
    import api.rest_pet as rp
    monkeypatch.setattr(rp, "_PET_DIR", tmp_path / "pet")
    r = client.post("/api/v1/pet/avatar", headers=HEADERS,
                    files={"file": ("a.exe", b"x", "application/octet-stream")})
    assert r.status_code == 400


def test_auth_required(client):
    assert client.get("/api/v1/pet/avatar").status_code == 401


def test_get_without_upload_returns_404(client, monkeypatch, tmp_path):
    import api.rest_pet as rp
    monkeypatch.setattr(rp, "_PET_DIR", tmp_path / "pet")
    assert client.get("/api/v1/pet/avatar", headers=HEADERS).status_code == 404
