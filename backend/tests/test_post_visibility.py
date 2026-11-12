"""帖子可见范围：public 全部可见 / friends 仅互关好友 / private 仅自己。

同时回归「关注不等于好友、互关才是好友」的语义。
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app


def _login(client: TestClient, username: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _fresh(client: TestClient) -> dict:
    name = f"v{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register",
                json={"username": name, "password": "secret123", "nickname": "可见性测试"})
    return _login(client, name, "secret123")


def _me_id(client: TestClient, headers: dict) -> int:
    return client.get("/api/users/me", headers=headers).json()["data"]["id"]


def _post(client: TestClient, headers: dict, visibility: str, title: str) -> int:
    r = client.post("/api/posts", headers=headers, json={
        "title": title, "content": f"{title} 的正文内容。", "city": "测试城",
        "location": "测试地", "images": [], "tags": ["可见性"],
        "visibility": visibility,
    })
    assert r.status_code == 200, r.text
    assert r.json()["data"]["visibility"] == visibility
    return r.json()["data"]["id"]


def _feed_ids(client: TestClient, headers: dict) -> set[int]:
    data = client.get("/api/posts/friends", headers=headers,
                      params={"page_size": 30}).json()["data"]
    return {p["id"] for p in data["items"]}


def test_admin_review_sees_all_and_filters_by_visibility():
    """管理端与用户端口径统一：审核列表看到可见范围字段，并可按三档筛选。"""
    with TestClient(app) as client:
        author = _fresh(client)
        admin = _login(client, "admin", "admin123")
        _post(client, author, "public", "审核-公开")
        _post(client, author, "friends", "审核-好友")
        _post(client, author, "private", "审核-私密")

        def titles(**params):
            rows = client.get("/api/admin/posts", headers=admin,
                              params={"page_size": 50, **params}).json()["data"]["items"]
            return {p["title"]: p["visibility"] for p in rows if p["title"].startswith("审核-")}

        all_rows = titles()
        assert all_rows == {"审核-公开": "public", "审核-好友": "friends",
                            "审核-私密": "private"}, "审核列表应能看到全部可见范围"

        assert titles(visibility="friends") == {"审核-好友": "friends"}
        assert titles(visibility="private") == {"审核-私密": "private"}
        assert titles(visibility="public") == {"审核-公开": "public"}

        # 非法筛选值被拒绝
        r = client.get("/api/admin/posts", headers=admin, params={"visibility": "wat"})
        assert r.status_code == 400


def test_visibility_public_friends_private():
    with TestClient(app) as client:
        author = _fresh(client)
        viewer = _fresh(client)
        author_id, viewer_id = _me_id(client, author), _me_id(client, viewer)

        pub = _post(client, author, "public", "公开动态")
        fr = _post(client, author, "friends", "好友动态")
        pv = _post(client, author, "private", "私密动态")

        # 1) 陌生人：只能看公开动态；好友/私密动态按「不存在」处理
        assert client.get(f"/api/posts/{pub}", headers=viewer).status_code == 200
        assert client.get(f"/api/posts/{fr}", headers=viewer).status_code == 404
        assert client.get(f"/api/posts/{pv}", headers=viewer).status_code == 404
        # 陌生人不能点赞 / 评论不可见的动态
        assert client.post(f"/api/posts/{pv}/like", headers=viewer).status_code == 404
        assert client.post(f"/api/posts/{fr}/comments", headers=viewer,
                           json={"content": "不该成功"}).status_code == 404

        # 2) 作者本人：三条都能看，动态流里都有
        assert client.get(f"/api/posts/{pv}", headers=author).status_code == 200
        assert {pub, fr, pv} <= _feed_ids(client, author)

        # 3) 单向关注：仍不是好友 → 看不到「好友可见」
        client.post(f"/api/users/{author_id}/follow", headers=viewer)
        assert viewer_id not in {u["id"] for u in client.get(
            "/api/users/friends", headers=author).json()["data"]}
        assert client.get(f"/api/posts/{fr}", headers=viewer).status_code == 404
        # 但公开动态会进入对方动态流
        assert pub in _feed_ids(client, viewer)
        assert fr not in _feed_ids(client, viewer)

        # 4) 作者回关 → 互关成为好友，好友可见放开
        client.post(f"/api/users/{viewer_id}/follow", headers=author)
        friends = client.get("/api/users/friends", headers=viewer).json()["data"]
        assert any(f["id"] == author_id and f["mutual"] for f in friends)
        assert client.get(f"/api/posts/{fr}", headers=viewer).status_code == 200
        assert fr in _feed_ids(client, viewer)
        # 私密动态始终只有作者能看到
        assert client.get(f"/api/posts/{pv}", headers=viewer).status_code == 404
        assert pv not in _feed_ids(client, viewer)


def test_moments_reports_friend_count_and_visibility_label():
    with TestClient(app) as client:
        a = _fresh(client)
        b = _fresh(client)
        a_id, b_id = _me_id(client, a), _me_id(client, b)
        client.post(f"/api/users/{b_id}/follow", headers=a)
        data = client.get("/api/posts/friends", headers=a).json()["data"]
        assert data["following_count"] == 1
        assert data["friends_count"] == 0, "单向关注好友数应为 0"

        client.post(f"/api/users/{a_id}/follow", headers=b)
        data = client.get("/api/posts/friends", headers=a).json()["data"]
        assert data["friends_count"] == 1, "互关后好友数应为 1"


def test_public_feed_hides_non_public_posts():
    with TestClient(app) as client:
        author = _fresh(client)
        viewer = _fresh(client)
        pub = _post(client, author, "public", "公开广场动态")
        fr = _post(client, author, "friends", "好友广场动态")
        pv = _post(client, author, "private", "私密广场动态")

        ids = {p["id"] for p in client.get(
            "/api/posts", headers=viewer, params={"page_size": 30}).json()["data"]["items"]}
        assert pub in ids
        assert fr not in ids and pv not in ids, "广场流不应出现非公开动态"

        # 广场是「公开内容」视图：作者本人浏览广场也不会看到自己的非公开动态
        own_square = {p["id"] for p in client.get(
            "/api/posts", headers=author, params={"page_size": 30}).json()["data"]["items"]}
        assert pub in own_square
        assert fr not in own_square and pv not in own_square
        # 自己的主页仍能看到全部（便于管理）
        own_profile = {p["id"] for p in client.get(
            "/api/posts", headers=author,
            params={"author_id": _me_id(client, author), "page_size": 30}
        ).json()["data"]["items"]}
        assert {pub, fr, pv} <= own_profile

        # 私密动态所在城市不进入城市聚合（用唯一城市名验证，避免受其他用例干扰）
        secret_city = f"私密城{uuid.uuid4().hex[:6]}"
        r = client.post("/api/posts", headers=author, json={
            "title": "私密城市动态", "content": "正文", "city": secret_city,
            "location": "", "images": [], "tags": [], "visibility": "private"})
        assert r.status_code == 200
        cities = {c["city"] for c in client.get("/api/posts/cities").json()["data"]}
        assert secret_city not in cities, "非公开动态的城市不应出现在城市筛选里"
