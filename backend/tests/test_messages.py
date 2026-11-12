"""消息中心与好友：点赞/收藏/评论/关注都会产生站内消息。"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app


def _login(client: TestClient, username: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _fresh(client: TestClient) -> dict:
    name = f"m{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register",
                json={"username": name, "password": "secret123", "nickname": "消息测试"})
    return _login(client, name, "secret123")


def _create_post(client: TestClient, headers: dict) -> int:
    """以当前身份发一条动态，返回 id（保证作者就是自己，便于断言消息归属）。"""
    r = client.post("/api/posts", headers=headers, json={
        "title": "消息中心测试动态", "content": "测试点赞/评论/收藏会生成站内消息。",
        "city": "成都", "location": "成都", "images": [], "tags": ["测试"]})
    return r.json()["data"]["id"]


def test_like_and_follow_generate_messages():
    with TestClient(app) as client:
        demo = _login(client, "demo", "demo123")
        other = _fresh(client)

        demo_id = client.get("/api/users/me", headers=demo).json()["data"]["id"]
        pid = _create_post(client, demo)

        # 他人点赞 / 评论 / 关注
        r = client.post(f"/api/posts/{pid}/like", headers=other)
        assert r.json()["data"]["liked"] is True
        client.post(f"/api/posts/{pid}/comments", headers=other, json={"content": "写得真好"})
        r = client.post(f"/api/users/{demo_id}/follow", headers=other)
        assert r.json()["data"]["following"] is True

        data = client.get("/api/messages", headers=demo).json()["data"]
        kinds = {m["kind"] for m in data["items"]}
        assert {"like", "comment", "follow"} <= kinds, f"实际 kinds={kinds}"
        assert data["unread"] >= 3
        assert "like" in data["counts"]

        # 全部已读
        res = client.post("/api/messages/read", headers=demo).json()["data"]
        assert res["unread"] == 0


def test_collect_sends_receipt_to_self():
    with TestClient(app) as client:
        me = _fresh(client)
        pid = _create_post(client, me)
        client.post(f"/api/posts/{pid}/collect", headers=me)
        data = client.get("/api/messages", headers=me).json()["data"]
        assert any(m["kind"] == "collect" for m in data["items"]), "收藏成功应有回执消息"


def test_friends_and_discover():
    with TestClient(app) as client:
        a = _fresh(client)
        b = _fresh(client)
        b_id = client.get("/api/users/me", headers=b).json()["data"]["id"]
        a_id = client.get("/api/users/me", headers=a).json()["data"]["id"]
        client.post(f"/api/users/{b_id}/follow", headers=a)

        # 单向关注：只是「关注」，还不算好友
        friends = client.get("/api/users/friends", headers=a).json()["data"]
        assert all(f["id"] != b_id for f in friends), "单向关注不应成为好友"
        following = client.get("/api/users/following", headers=a).json()["data"]
        assert any(f["id"] == b_id for f in following), "应出现在「我的关注」里"

        # 对方回关 → 互相关注才成为好友，双方好友列表都能看到对方
        client.post(f"/api/users/{a_id}/follow", headers=b)
        assert any(f["id"] == b_id
                   for f in client.get("/api/users/friends", headers=a).json()["data"])
        assert any(f["id"] == a_id
                   for f in client.get("/api/users/friends", headers=b).json()["data"])

        discover = client.get("/api/users/discover", headers=a).json()["data"]
        assert all(u["id"] != b_id for u in discover), "已关注的人不应再出现在推荐里"


def test_cannot_follow_self():
    with TestClient(app) as client:
        me = _fresh(client)
        my_id = client.get("/api/users/me", headers=me).json()["data"]["id"]
        r = client.post(f"/api/users/{my_id}/follow", headers=me)
        assert r.status_code == 400
