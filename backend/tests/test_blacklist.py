"""黑名单：管理员拉黑后，该用户不能发帖 / 点赞 / 评论 / 收藏 / 关注。"""
from __future__ import annotations


async def _login(client, username="demo", password="demo123"):
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _make_post(client, headers, title="黑名单用例动态") -> dict:
    r = await client.post("/api/posts", headers=headers, json={
        "title": title, "content": f"{title} 正文", "city": "成都",
        "location": "", "tags": [], "images": [],
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _register(client, username: str) -> dict:
    r = await client.post("/api/auth/register", json={
        "username": username, "password": "test1234", "nickname": f"黑名单测试-{username}",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def test_blacklist_blocks_community_actions(client, auth_headers):
    admin_headers = await _login(client, "admin", "admin123")
    victim_headers = await _register(client, "ban_victim")
    me = (await client.get("/api/users/me", headers=victim_headers)).json()["data"]
    victim_id = me["id"]

    other_post = await _make_post(client, auth_headers, "黑名单-他人动态")

    # 拉黑前：发帖 / 点赞 / 评论 / 收藏 / 关注都正常
    assert (await client.post("/api/posts", headers=victim_headers, json={
        "title": "拉黑前", "content": "拉黑前正常发布", "city": "成都",
        "location": "", "tags": [], "images": [],
    })).status_code == 200
    assert (await client.post(f"/api/posts/{other_post['id']}/like",
                              headers=victim_headers)).status_code == 200
    comment = (await client.post(f"/api/posts/{other_post['id']}/comments",
                                 headers=victim_headers,
                                 json={"content": "拉黑前留言"})).json()["data"]
    assert (await client.post(f"/api/posts/{other_post['id']}/collect",
                              headers=victim_headers)).status_code == 200
    author_id = other_post["author"]["id"]
    assert (await client.post(f"/api/users/{author_id}/follow",
                              headers=victim_headers)).status_code == 200

    # 管理员拉黑
    added = await client.post("/api/admin/blacklist", headers=admin_headers,
                              json={"user_id": victim_id, "reason": "测试：恶意刷屏"})
    assert added.status_code == 200, added.text
    assert added.json()["data"]["banned"] is True
    assert added.json()["data"]["ban_reason"] == "测试：恶意刷屏"

    listed = (await client.get("/api/admin/blacklist", headers=admin_headers)).json()["data"]
    assert any(u["id"] == victim_id for u in listed)

    # 拉黑后：五类写操作全部 403
    for name, resp in (
        ("发帖", await client.post("/api/posts", headers=victim_headers, json={
            "title": "拉黑后", "content": "不应成功", "city": "成都",
            "location": "", "tags": [], "images": []})),
        ("点赞", await client.post(f"/api/posts/{other_post['id']}/like", headers=victim_headers)),
        ("评论", await client.post(f"/api/posts/{other_post['id']}/comments",
                                 headers=victim_headers, json={"content": "不应成功"})),
        ("评论编辑", await client.put(f"/api/posts/comments/{comment['id']}",
                                 headers=victim_headers, json={"content": "不应成功"})),
        ("收藏", await client.post(f"/api/posts/{other_post['id']}/collect",
                                 headers=victim_headers)),
        ("关注", await client.post(f"/api/users/{author_id}/follow", headers=victim_headers)),
    ):
        assert resp.status_code == 403, f"{name} 被拉黑后应被拒绝，实际 {resp.status_code}"
        assert "黑名单" in resp.text

    # 自己的账号信息里能看到被拉黑状态（前端据此禁用发布按钮并提示）
    me_after = (await client.get("/api/users/me", headers=victim_headers)).json()["data"]
    assert me_after["banned"] is True

    # 解封后恢复
    removed = await client.delete(f"/api/admin/blacklist/{victim_id}", headers=admin_headers)
    assert removed.status_code == 200
    assert removed.json()["data"]["banned"] is False
    after = await client.post("/api/posts", headers=victim_headers, json={
        "title": "解封后", "content": "解封后正常发布", "city": "成都",
        "location": "", "tags": [], "images": [],
    })
    assert after.status_code == 200
    assert (await client.get("/api/admin/blacklist", headers=admin_headers)).json()["data"] == []

    # 清理本用例产生的数据，避免污染其它用例（动态列表按时间倒序，残留会改变首条）
    for pid in (other_post["id"], after.json()["data"]["id"]):
        assert (await client.delete(f"/api/admin/posts/{pid}",
                                    headers=admin_headers)).status_code == 200
    victim_posts = (await client.get("/api/posts", headers=victim_headers,
                                     params={"mine": True})).json()["data"]["items"]
    for p in victim_posts:
        await client.delete(f"/api/admin/posts/{p['id']}", headers=admin_headers)


async def test_blacklist_guardrails_and_permission(client, auth_headers):
    admin_headers = await _login(client, "admin", "admin123")
    admin_me = (await client.get("/api/users/me", headers=admin_headers)).json()["data"]

    # 普通用户无权访问黑名单管理
    assert (await client.get("/api/admin/blacklist", headers=auth_headers)).status_code == 403
    assert (await client.get("/api/admin/users", headers=auth_headers)).status_code == 403

    # 不能拉黑自己 / 管理员账号
    self_ban = await client.post("/api/admin/blacklist", headers=admin_headers,
                                 json={"user_id": admin_me["id"], "reason": ""})
    assert self_ban.status_code == 400
    # 不存在用户 → 404
    missing = await client.post("/api/admin/blacklist", headers=admin_headers,
                                json={"user_id": 999999, "reason": ""})
    assert missing.status_code == 404

    # 用户检索：关键字命中 + banned 过滤
    users = (await client.get("/api/admin/users", headers=admin_headers,
                              params={"keyword": "demo"})).json()["data"]
    assert any(u["username"] == "demo" for u in users)
    banned_only = (await client.get("/api/admin/users", headers=admin_headers,
                                    params={"banned": 1})).json()["data"]
    assert all(u["banned"] for u in banned_only)
