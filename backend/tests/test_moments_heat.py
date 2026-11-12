"""动态（朋友圈）/ 热度计数 / 图片落盘 / 知识库概览 单测。"""
from __future__ import annotations

import base64

_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        '<rect width="64" height="64" fill="#22c55e"/></svg>')


async def _login(client, username="demo", password="demo123"):
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _new_post(client, headers, title: str, images: list[str] | None = None) -> dict:
    r = await client.post("/api/posts", headers=headers, json={
        "title": title, "content": f"{title} 正文", "city": "成都",
        "location": "", "tags": [], "images": images or [],
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_heat_like_counts_only_once(client, auth_headers):
    """热度规则：首次点赞 +1；取消 -1；取消后再赞不再累加（无效）。"""
    other = await _new_post(client, await _login(client, "admin", "admin123"), "热度-他人的动态")
    post_id = other["id"]
    base = other["heat"]

    first = (await client.post(f"/api/posts/{post_id}/like", headers=auth_headers)).json()["data"]
    cancel = (await client.post(f"/api/posts/{post_id}/like", headers=auth_headers)).json()["data"]
    again = (await client.post(f"/api/posts/{post_id}/like", headers=auth_headers)).json()["data"]

    assert first["liked"] is True and first["heat"] == base + 1
    assert cancel["liked"] is False and cancel["heat"] == base
    assert again["liked"] is True and again["heat"] == base, "取消后再赞不应重复加热度"
    assert again["like_count"] == 1                      # 点赞数正常计数（+1 → -1 → +1）


async def test_heat_comment_and_collect(client, auth_headers):
    other = await _new_post(client, await _login(client, "admin", "admin123"), "热度-评论收藏")
    post_id = other["id"]
    base = other["heat"]

    created = (await client.post(f"/api/posts/{post_id}/comments", headers=auth_headers,
                                 json={"content": "热度测试留言"})).json()["data"]
    after_comment = (await client.get(f"/api/posts/{post_id}", headers=auth_headers)).json()["data"]
    assert after_comment["heat"] == base + 1             # 评论 +1

    edited = await client.put(f"/api/posts/comments/{created['id']}", headers=auth_headers,
                              json={"content": "编辑后的留言"})
    assert edited.status_code == 200 and edited.json()["data"]["content"] == "编辑后的留言"
    after_edit = (await client.get(f"/api/posts/{post_id}", headers=auth_headers)).json()["data"]
    assert after_edit["heat"] == after_comment["heat"]   # 编辑不改热度

    assert (await client.delete(f"/api/posts/comments/{created['id']}",
                                headers=auth_headers)).status_code == 200
    after_del = (await client.get(f"/api/posts/{post_id}", headers=auth_headers)).json()["data"]
    assert after_del["heat"] == base                     # 删除评论回退

    collected = (await client.post(f"/api/posts/{post_id}/collect", headers=auth_headers)).json()["data"]
    assert collected["heat"] == base + 1                 # 收藏 +1
    await client.post(f"/api/posts/{post_id}/collect", headers=auth_headers)
    back = (await client.get(f"/api/posts/{post_id}", headers=auth_headers)).json()["data"]
    assert back["heat"] == base                          # 取消收藏回退


async def test_moments_feed_has_own_and_following(client, auth_headers):
    admin_headers = await _login(client, "admin", "admin123")
    other = await _new_post(client, admin_headers, "动态流-他人")
    mine = await _new_post(client, auth_headers, "动态流-我自己")

    res = await client.get("/api/posts/friends", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    ids = [p["id"] for p in data["items"]]
    assert mine["id"] in ids, "自己的动态应出现在动态流"
    assert "content" in data["items"][0], "动态流应带完整正文"
    assert "following_count" in data

    # 关注 admin 后，其动态也进入动态流
    admin_id = other["author"]["id"]
    await client.post(f"/api/users/{admin_id}/follow", headers=auth_headers)
    after = (await client.get("/api/posts/friends", headers=auth_headers)).json()["data"]
    assert other["id"] in [p["id"] for p in after["items"]], "关注后其动态应出现在动态流"


async def test_post_images_local_path_dropped_and_data_url_stored(client, auth_headers):
    post = await _new_post(client, auth_headers, "图片落盘-测试", images=[
        "C:\\Users\\somebody\\Pictures\\local.png",              # 本地磁盘路径 → 丢弃
        "data:image/svg+xml;utf8," + _SVG,                        # data URL → 落盘
        "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 30).decode(),
    ])
    images = post["images"]
    assert images, "合法的 data URL 应被落盘"
    assert all(u.startswith("/api/media/") for u in images), images
    assert not any(u.startswith("C:") for u in images), "本地磁盘路径不应写入数据库"

    served = await client.get(images[0])
    assert served.status_code == 200 and served.content


async def test_avatar_and_cover_materialized_to_backend_path(client, auth_headers):
    # data URL 头像 → 落盘为后端调用路径
    r = await client.put("/api/users/me", headers=auth_headers,
                         json={"avatar": "data:image/svg+xml;utf8," + _SVG})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["avatar"].startswith("/api/media/")

    # 本地磁盘路径 → 明确报错（不再把路径文字存库）
    bad = await client.put("/api/users/me", headers=auth_headers,
                           json={"avatar": "D:\\pics\\me.png"})
    assert bad.status_code == 400
    assert "本地磁盘路径" in bad.text

    # 背景图同样落盘
    cover = await client.put("/api/users/me", headers=auth_headers,
                             json={"cover": "data:image/svg+xml;utf8," + _SVG})
    assert cover.status_code == 200
    assert cover.json()["data"]["cover"].startswith("/api/media/")


async def test_knowledge_overview_for_normal_user(client, auth_headers):
    r = await client.get("/api/knowledge/overview", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["vector_backend"] in ("memory", "pgvector")
    assert data["chunks"] >= 0 and "recent" in data
    assert data["embedding"]["provider"]
    assert "chunking" in data and "retrieval" in data
