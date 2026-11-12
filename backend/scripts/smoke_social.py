"""端到端冒烟：知识库概览 / 动态流 / 热度计数 / 图片落盘。

前置：后端已在 127.0.0.1:8000 运行。
用法：python scripts/smoke_social.py
"""
from __future__ import annotations

import base64
import json

import httpx

BASE = "http://127.0.0.1:8000"
_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        '<rect width="64" height="64" fill="#22c55e"/></svg>')


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=60) as c:
        demo = c.post("/api/auth/login", json={"username": "demo", "password": "demo123"}).json()["data"]
        admin = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["data"]
        uh = {"Authorization": f"Bearer {demo['access_token']}"}
        ah = {"Authorization": f"Bearer {admin['access_token']}"}
        me_id = demo["user"]["id"]

        # 1) 知识库概览（普通用户只读）
        kb = c.get("/api/knowledge/overview", headers=uh).json()["data"]
        print(f"[knowledge] ready={kb['ready']} backend={kb['vector_backend']} "
              f"docs={kb['documents']} chunks={kb['chunks']} 模型={kb['embedding']['provider']}")
        print(f"            最近文档: {[d['title'] for d in kb['recent'][:3]]}")

        # 2) 头像确实由后端文件夹提供
        avatar = demo["user"]["avatar"]
        mid = avatar.rsplit("/", 1)[-1] if avatar.startswith("/api/media/") else ""
        av = c.get(f"/api/media/{mid}") if mid else None
        print(f"[avatar] avatar字段={avatar} "
              f"{'直接取图 HTTP ' + str(av.status_code) + ' ' + str(av.headers.get('content-type','')) + ' ' + str(len(av.content)) + 'B' if av else '非后端路径'}")

        # 3) 用「全新的动态 + 未点过赞的账号」验证热度规则（避免历史状态干扰）
        target = c.post("/api/posts", headers=uh, json={
            "title": "冒烟：热度基线动态", "content": "用于验证热度计数规则",
            "city": "成都", "location": "", "tags": [], "images": [],
        }).json()["data"]
        pid = target["id"]
        base_heat = target["heat"]
        print(f"[moments] 目标动态#{pid} 作者={target['author']['nickname']} 初始热度={base_heat}")

        # 4) 热度规则：点赞只计一次、取消再赞无效（actor 用 admin）
        h1 = c.post(f"/api/posts/{pid}/like", headers=ah).json()["data"]
        h2 = c.post(f"/api/posts/{pid}/like", headers=ah).json()["data"]
        h3 = c.post(f"/api/posts/{pid}/like", headers=ah).json()["data"]
        print(f"[heat.like] 首次点赞 {h1} → 取消 {h2} → 再赞 {h3}")
        assert h1["heat"] == base_heat + 1, "首次点赞应 +1"
        assert h2["heat"] == base_heat, "取消点赞应回退"
        assert h3["heat"] == base_heat, "取消后再赞不应重复加热度（无效）"

        # 5) 热度规则：评论 +1、收藏 +1
        created = c.post(f"/api/posts/{pid}/comments", headers=ah,
                         json={"content": "冒烟：这条评论用于验证热度计数"}).json()["data"]
        after_comment = c.get(f"/api/posts/{pid}", headers=uh).json()["data"]["heat"]
        c.put(f"/api/posts/comments/{created['id']}", headers=ah,
              json={"content": "冒烟：编辑后的评论"})
        after_edit = c.get(f"/api/posts/{pid}", headers=uh).json()["data"]["heat"]
        c.delete(f"/api/posts/comments/{created['id']}", headers=ah)
        after_del = c.get(f"/api/posts/{pid}", headers=uh).json()["data"]["heat"]
        col = c.post(f"/api/posts/{pid}/collect", headers=ah).json()["data"]
        c.post(f"/api/posts/{pid}/collect", headers=ah)
        print(f"[heat.comment] 评论后 {after_comment}（编辑后 {after_edit}）删除后 {after_del}；收藏 {col}")
        assert after_comment == base_heat + 1, "评论应 +1"
        assert after_edit == after_comment, "编辑评论不应改变热度"
        assert after_del == base_heat, "删除评论应回退"
        c.delete(f"/api/posts/{pid}", headers=uh)

        # 6) 图片落盘：本地磁盘路径丢弃、data URL 落盘
        post = c.post("/api/posts", headers=uh, json={
            "title": "冒烟：图片落盘", "content": "验证本地路径与 data URL 的处理",
            "city": "成都", "location": "", "tags": ["冒烟"],
            "images": ["C:\\Users\\decade\\Pictures\\local.png",
                       "data:image/svg+xml;utf8," + _SVG,
                       "data:image/png;base64," + base64.b64encode(
                           b"\x89PNG\r\n\x1a\n" + b"\x00" * 40).decode()],
        }).json()["data"]
        print(f"[images] 提交 3 个（本地路径/data:svg/data:png）→ 入库 {post['images']}")
        saved = c.get(f"/api/posts/{post['id']}", headers=uh).json()["data"]["images"]
        assert all(u.startswith("/api/media/") or u.startswith("http") for u in saved), saved
        assert not any(u.startswith("C:") for u in saved), "本地磁盘路径不应入库"
        c.delete(f"/api/posts/{post['id']}", headers=uh)

        # 7) 动态流包含自己的动态
        mine = c.post("/api/posts", headers=uh, json={
            "title": "冒烟：我的动态", "content": "自己发布的动态应出现在动态流",
            "city": "重庆", "location": "", "tags": [], "images": [],
        }).json()["data"]
        feed = c.get("/api/posts/friends", headers=uh).json()["data"]
        ids = [p["id"] for p in feed["items"]]
        assert isinstance(feed.get("followers_count"), int), "动态流应返回粉丝数"
        print(f"[moments.feed] 共 {feed['total']} 条 · 已关注 {feed['following_count']} 人 · "
              f"粉丝 {feed['followers_count']} 人 · 含自己的动态={mine['id'] in ids}")
        c.delete(f"/api/posts/{mine['id']}", headers=uh)

        # 8) 动态页背景图：data URL → 落盘为后端路径，并可直接取图
        cover = c.put("/api/users/me", headers=uh,
                      json={"cover": "data:image/svg+xml;utf8," + _SVG}).json()["data"]["cover"]
        got = c.get(cover)
        print(f"[cover] 背景图字段={cover} 取图 HTTP {got.status_code} "
              f"{got.headers.get('content-type', '')} CSP={got.headers.get('content-security-policy', '')}")

        # 9) 管理员：文档上传开放状态 + 文档上传接口
        s = c.get("/api/admin/settings", headers=ah).json()["data"]
        print(f"[admin.settings] doc_upload_ready={s.get('doc_upload_ready')} "
              f"reason={s.get('doc_upload_reason')} backend={s.get('vector_backend')}")
        up = c.post("/api/media/upload_doc", headers=ah, params={"city": "通用"},
                    files={"file": ("smoke_note.txt",
                                    "冒烟知识文档\n\n一、门票 50 元。\n- 1 -\n".encode("utf-8"),
                                    "text/plain")})
        if up.status_code == 200:
            d = up.json()["data"]
            print(f"[upload_doc] {d['title']} 清洗 {d['clean']['clean_chars']} 字 · "
                  f"切片 {d['chunks']} · 总量 {d['total_chunks']} · {d['vector_backend']}")
        else:
            print("[upload_doc] 失败:", up.status_code, up.text[:160])

        print("\n全部冒烟断言通过")


if __name__ == "__main__":
    main()
