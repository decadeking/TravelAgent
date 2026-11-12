"""media-service（图片入库）与模型配置自检单测。"""
from __future__ import annotations

import io
import struct
import zlib


def _tiny_png() -> bytes:
    """生成一张 1x1 的合法 PNG（用于上传测试）。"""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\xff\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


async def _login(client, username="demo", password="demo123"):
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def test_upload_and_serve_media(client, auth_headers):
    png = _tiny_png()
    r = await client.post(
        "/api/media/upload",
        headers=auth_headers,
        params={"kind": "avatar"},
        files={"file": ("a.png", io.BytesIO(png), "image/png")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["url"] == f"/api/media/{data['id']}"
    assert data["mime"] == "image/png"

    # 对外提供：字节一致
    got = await client.get(data["url"])
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/png")
    assert got.content == png

    # 去重：同一内容再传一次返回同一 id
    r2 = await client.post("/api/media/upload", headers=auth_headers,
                           files={"file": ("b.png", io.BytesIO(png), "image/png")})
    assert r2.json()["data"]["id"] == data["id"]


async def test_upload_rejects_non_image(client, auth_headers):
    r = await client.post("/api/media/upload", headers=auth_headers,
                          files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")})
    assert r.status_code == 400


async def test_media_requires_auth(client):
    r = await client.get("/api/media/1")
    assert r.status_code in (200, 404)      # 读取公开
    r2 = await client.post("/api/media/upload",
                           files={"file": ("a.png", io.BytesIO(_tiny_png()), "image/png")})
    assert r2.status_code == 401            # 上传需登录


async def test_post_images_sync_into_db(client, auth_headers, monkeypatch):
    """种子帖子的外链配图可被同步入库，并改由 /api/media/ 提供（下载用替身，保证确定性）。"""
    from app.services.media_service import router as media_router

    async def _fake_download(url: str):
        return _tiny_png(), "image/png"

    monkeypatch.setattr(media_router, "_download", _fake_download)

    before = (await client.get("/api/posts", headers=auth_headers,
                              params={"page_size": 30})).json()["data"]
    before_ext = [u for it in before["items"] for u in it["images"]
                  if not u.startswith("/api/media/")]

    admin = await _login(client, "admin", "admin123")
    res = (await client.post("/api/admin/media/sync", headers=admin,
                             params={"limit": 80})).json()["data"]
    assert res["images_stored"] > 0

    after = (await client.get("/api/posts", headers=auth_headers,
                             params={"page_size": 30})).json()["data"]
    local = [u for it in after["items"] for u in it["images"]
             if u.startswith("/api/media/")]
    assert local, "同步后配图应全部改由本地媒体库提供"
    if before_ext:
        assert len(local) >= len(before_ext)
    got = await client.get(local[0])
    assert got.status_code == 200 and got.content


async def test_avatar_set_to_media_url(client, auth_headers):
    png = _tiny_png()
    up = await client.post("/api/media/upload", headers=auth_headers,
                           params={"kind": "avatar"},
                           files={"file": ("me.png", io.BytesIO(png), "image/png")})
    url = up.json()["data"]["url"]
    r = await client.put("/api/users/me", headers=auth_headers, json={"avatar": url})
    assert r.json()["data"]["avatar"] == url
    me = await client.get("/api/users/me", headers=auth_headers)
    assert me.json()["data"]["avatar"] == url


async def test_model_config_test_endpoint_without_key(client):
    """无密钥时自检应返回可读提示，而不是报错。"""
    import uuid
    name = f"t{uuid.uuid4().hex[:8]}"
    reg = await client.post("/api/auth/register",
                            json={"username": name, "password": "secret123", "nickname": "自检"})
    headers = {"Authorization": f"Bearer {reg.json()['data']['access_token']}"}
    r = await client.post("/api/users/model-config/test", headers=headers, json={})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ok"] is False
    assert "API Key" in data["message"]


async def test_media_sync_requires_admin(client):
    user = await _login(client, "demo", "demo123")
    assert (await client.post("/api/admin/media/sync", headers=user)).status_code == 403
    admin = await _login(client, "admin", "admin123")
    stats = (await client.get("/api/admin/media/stats", headers=admin)).json()["data"]
    assert "count" in stats and "mb" in stats


def test_model_chain_resolution():
    """展示用模型 id 必须解析成真实上游模型名，且带兜底候选。"""
    from app.common.runtime_config import default_llm, resolve_model_chain

    cfg = default_llm()
    chain = resolve_model_chain(cfg, "deepseek-v4-flash")
    assert chain[0] == "deepseek-v4-flash"
    assert "deepseek-chat" in chain          # 模型不存在时自动兜底

    chain2 = resolve_model_chain(cfg, "deepseek-4.1-flash")
    assert chain2[0] == "deepseek-4.1-flash"
    assert "deepseek-chat" in chain2

    # 未知 id 原样使用，不崩
    assert resolve_model_chain(cfg, "custom-model") == ["custom-model"]


def test_readable_upstream_errors():
    """上游错误必须翻译成用户能看懂的中文提示。"""
    from app.services.agent_service.llm.adapter import _is_model_missing, _readable_upstream_error

    assert "API Key" in _readable_upstream_error(401, "Authentication Fails").message
    assert "余额" in _readable_upstream_error(402, "Insufficient Balance").message
    assert "限流" in _readable_upstream_error(429, "rate limit").message

    assert _is_model_missing(400, '{"error":{"message":"Model Not Exist"}}') is True
    assert _is_model_missing(404, "model not found") is True
    assert _is_model_missing(401, "Model Not Exist") is False    # 鉴权错不切换模型