"""旅行吧（社交动态）与管理端单测。"""
from __future__ import annotations


async def _login(client, username="demo", password="demo123"):
    r = await client.post("/api/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def test_feed_list(client, auth_headers):
    r = await client.get("/api/posts", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] >= 10
    first = data["items"][0]
    assert first["images"] and first["author"]["nickname"]


async def test_post_detail_with_comments(client, auth_headers):
    listing = (await client.get("/api/posts", headers=auth_headers)).json()["data"]
    pid = listing["items"][0]["id"]
    detail = (await client.get(f"/api/posts/{pid}", headers=auth_headers)).json()["data"]
    assert detail["content"]
    assert isinstance(detail["comments"], list)
    assert detail["view_count"] >= 1


async def test_like_collect_comment_flow(client, auth_headers):
    listing = (await client.get("/api/posts", headers=auth_headers)).json()["data"]
    item = listing["items"][0]
    pid = item["id"]
    liked0, collected0 = item["liked"], item["collected"]

    r1 = await client.post(f"/api/posts/{pid}/like", headers=auth_headers)
    assert r1.json()["data"]["liked"] is (not liked0)
    r2 = await client.post(f"/api/posts/{pid}/like", headers=auth_headers)
    assert r2.json()["data"]["liked"] is liked0

    c = await client.post(f"/api/posts/{pid}/collect", headers=auth_headers)
    assert c.json()["data"]["collected"] is (not collected0)

    cm = await client.post(f"/api/posts/{pid}/comments", headers=auth_headers,
                           json={"content": "自动化测试留言"})
    cid = cm.json()["data"]["id"]
    assert cm.json()["data"]["content"] == "自动化测试留言"
    await client.delete(f"/api/posts/comments/{cid}", headers=auth_headers)


async def test_create_edit_delete_own_post(client, auth_headers):
    payload = {"title": "测试动态", "content": "这是自动化测试发布的动态内容",
               "city": "成都", "location": "测试地点", "images": [], "tags": ["测试"]}
    created = (await client.post("/api/posts", json=payload, headers=auth_headers)).json()["data"]
    pid = created["id"]
    assert created["author"]["nickname"]

    upd = (await client.put(f"/api/posts/{pid}", headers=auth_headers,
                            json={**payload, "title": "已修改标题"})).json()["data"]
    assert upd["title"] == "已修改标题"

    d = await client.delete(f"/api/posts/{pid}", headers=auth_headers)
    assert d.json()["data"]["deleted"] == pid


async def test_admin_permission_and_stats(client):
    admin = await _login(client, "admin", "admin123")
    user = await _login(client, "demo", "demo123")

    forbidden = await client.get("/api/admin/stats", headers=user)
    assert forbidden.status_code == 403

    stats = (await client.get("/api/admin/stats", headers=admin)).json()["data"]
    assert stats["posts"] >= 10 and stats["kb_documents"] > 0


async def test_admin_moderation(client):
    admin = await _login(client, "admin", "admin123")
    listing = (await client.get("/api/admin/posts", headers=admin)).json()["data"]
    pid = listing["items"][0]["id"]
    r = await client.put(f"/api/admin/posts/{pid}/status?status=rejected", headers=admin)
    assert r.json()["data"]["status"] == "rejected"
    await client.put(f"/api/admin/posts/{pid}/status?status=published", headers=admin)


async def test_admin_llm_and_rag_settings(client):
    admin = await _login(client, "admin", "admin123")
    s = (await client.get("/api/admin/settings", headers=admin)).json()["data"]
    assert "llm" in s and "rag" in s
    assert s["llm"]["api_key"] == ""       # 不回传密钥

    r = await client.put("/api/admin/settings/llm", headers=admin,
                         json={"temperature": 0.5, "default_model": "mock"})
    assert r.json()["data"]["temperature"] == 0.5

    rag = await client.put("/api/admin/settings/rag", headers=admin,
                           json={"chunk_size": 300, "topk": 4})
    assert rag.json()["data"]["chunk_size"] == 300
    assert rag.json()["data"]["kb_chunks"] > 0      # 参数变更后已重建索引


async def test_admin_kb_management_and_search(client):
    admin = await _login(client, "admin", "admin123")
    before = (await client.get("/api/admin/kb", headers=admin)).json()["data"]
    created = (await client.post("/api/admin/kb", headers=admin, json={
        "city": "成都", "title": "测试知识条目",
        "content": "成都自动化测试知识：某博物馆周一闭馆，门票 60 元。"})).json()["data"]
    assert created["id"]

    hits = (await client.post("/api/admin/kb/search?query=博物馆 周一闭馆 门票&city=成都",
                              headers=admin)).json()["data"]
    assert hits["hits"], "RAG 检索应命中新建的知识条目"

    await client.delete(f"/api/admin/kb/{created['id']}", headers=admin)
    after = (await client.get("/api/admin/kb", headers=admin)).json()["data"]
    assert len(after) == len(before)


async def test_weather_tool_returns_real_or_fallback(client):
    r = await client.get("/api/tools/weather", params={"city": "成都", "days": 3})
    data = r.json()["data"]
    assert data["forecast"] and len(data["forecast"]) == 3
    assert data["source"] in ("open-meteo", "mock")


async def test_geocode_tool(client):
    data = (await client.get("/api/tools/geocode", params={"query": "成都"})).json()["data"]
    assert data["found"] is True
    assert abs(data["lat"] - 30.57) < 0.5 and abs(data["lon"] - 104.07) < 0.5


async def test_profile_update_avatar(client, auth_headers):
    r = await client.put("/api/users/me", headers=auth_headers,
                         json={"nickname": "体验官改名", "avatar": "https://example.com/a.png",
                               "bio": "新简介"})
    data = r.json()["data"]
    assert data["nickname"] == "体验官改名"
    assert data["avatar"] == "https://example.com/a.png"


async def test_my_comments(client, auth_headers):
    listing = (await client.get("/api/posts", headers=auth_headers)).json()["data"]
    pid = listing["items"][0]["id"]
    cm = await client.post(f"/api/posts/{pid}/comments", headers=auth_headers,
                           json={"content": "我的评论测试"})
    cid = cm.json()["data"]["id"]
    mine = (await client.get("/api/posts/mine/comments", headers=auth_headers)).json()["data"]
    hit = next((c for c in mine if c["content"] == "我的评论测试"), None)
    assert hit is not None
    assert hit["post_id"] == pid and hit["post_title"]
    await client.delete(f"/api/posts/comments/{cid}", headers=auth_headers)


async def test_user_model_config(client):
    """用户级模型配置：只暴露密钥与模型，其余为固定配置。用新注册用户隔离影响。"""
    import uuid
    name = f"m{uuid.uuid4().hex[:8]}"
    reg = await client.post("/api/auth/register",
                            json={"username": name, "password": "secret123", "nickname": "模型测试"})
    headers = {"Authorization": f"Bearer {reg.json()['data']['access_token']}"}

    cfg = (await client.get("/api/users/model-config", headers=headers)).json()["data"]
    ids = {m["id"] for m in cfg["models"]}
    assert ids == {"deepseek-v4-flash", "deepseek-4.1-flash"}
    assert cfg["has_api_key"] is False
    assert "base_url" not in cfg and "temperature" not in cfg   # 固定配置不下发

    r = await client.put("/api/users/model-config", headers=headers,
                         json={"api_key": "sk-test-123", "model": "deepseek-4.1-flash"})
    assert r.json()["data"]["has_api_key"] is True

    cfg2 = (await client.get("/api/users/model-config", headers=headers)).json()["data"]
    assert cfg2["has_own_api_key"] is True
    assert cfg2["selected_model"] == "deepseek-4.1-flash"
