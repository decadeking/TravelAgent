"""端到端冒烟：MCP 状态 / RAG 自检 / 文档上传 / 行程提醒 / 逆地理编码。

前置：后端已在 127.0.0.1:8000 运行（backend/.env 已设 MCP_ENABLED=1）。
用法：python scripts/smoke_e2e.py
"""
from __future__ import annotations

import io
import json
import sys

import httpx

sys.path.insert(0, ".")
BASE = "http://127.0.0.1:8000"


def show(tag: str, data) -> None:
    print(f"[{tag}] {json.dumps(data, ensure_ascii=False)[:400]}")


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=60) as c:
        demo = c.post("/api/auth/login", json={"username": "demo", "password": "demo123"})
        admin = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert demo.status_code == 200 and admin.status_code == 200, "登录失败"
        uh = {"Authorization": f"Bearer {demo.json()['data']['access_token']}"}
        ah = {"Authorization": f"Bearer {admin.json()['data']['access_token']}"}

        show("health", c.get("/api/health").json()["data"])
        show("mcp.status", c.get("/api/mcp/status", headers=uh).json()["data"])
        tools = c.get("/api/mcp/tools", headers=ah).json()["data"]
        print("[mcp.tools]", [t["name"] for t in tools["tools"]])

        # RAG 全链路自检
        st = c.post("/api/admin/kb/selftest", headers=ah)
        body = st.json()["data"]
        print("[rag.selftest] passed =", body["passed"])
        for s in body["stages"]:
            print(f"   - {s['name']}: {'有效' if s['ok'] else '无效'} | {json.dumps(s['detail'], ensure_ascii=False)[:160]}")

        # 上传知识文档（txt）
        doc = ("大理旅行备忘\n\n一、洱海环湖：骑行一圈约 130 公里，电动车日租 80 元。\n"
               "二、苍山索道：往返 200 元，开放时间 08:30-17:00。\n"
               "三、喜洲古镇：免费，适合半日游，品尝破酥粑粑。\n- 1 -\n")
        up = c.post("/api/media/upload_doc", headers=uh, params={"city": "大理"},
                    files={"file": ("dali_note.txt", io.BytesIO(doc.encode("utf-8")), "text/plain")})
        if up.status_code == 200:
            d = up.json()["data"]
            print(f"[upload_doc] {d['title']} 清洗 {d['clean']['clean_chars']} 字 · "
                  f"切片 {d['chunks']} · 总量 {d['total_chunks']} · {d['vector_backend']}")
            print("            preview:", d["preview"].replace("\n", " ")[:80])
        else:
            print("[upload_doc] 失败:", up.status_code, up.text[:200])

        # 检索命中刚上传的内容
        hits = c.post("/api/admin/kb/search", headers=ah, params={"query": "大理 洱海 骑行"}).json()["data"]
        print("[kb.search] hits:", [(h["title"], h["score"]) for h in hits["hits"][:3]])

        # 带出发日期的行程创建 → 自动写入提醒
        from datetime import date, timedelta
        start = (date.today() + timedelta(days=10)).isoformat()
        trip = c.post("/api/trips", headers=uh, json={
            "title": "大理三日游", "destination": "大理", "days": 3, "budget": 2500,
            "status": "draft", "remark": "骑行洱海，注意防晒", "start_date": start,
            "day_list": [],
        })
        tdata = trip.json()["data"]
        print("[trip.create]", {k: tdata[k] for k in ("id", "title", "start_date", "total_cost")})
        rem = c.get("/api/agent/reminders", headers=uh).json()["data"]
        mine = [r for r in rem if r.get("source") == "trip"]
        print("[reminders]", [(r["title"], r["remind_at"], r["status"]) for r in mine[:4]])

        # 逆地理编码（地图地点 API）
        rg = c.get("/api/tools/reverse_geocode", headers=uh, params={"lat": 25.6065, "lon": 100.2676}).json()["data"]
        show("reverse_geocode", rg)

        # 清理：删除本次测试行程
        if tdata.get("id"):
            c.delete(f"/api/trips/{tdata['id']}", headers=uh)
            print("[cleanup] 已删除测试行程", tdata["id"])

    check_desktop_fire()


def check_desktop_fire() -> None:
    """校验「提醒到期 → 站内通知 + 桌面通知」这条链路（desktop=1 的提醒）。"""
    import asyncio
    from datetime import datetime, timedelta

    async def _run() -> None:
        from sqlalchemy import func, select

        from app.db.models import Notification, Reminder, User
        from app.db.session import SessionLocal
        from app.services.agent_service.reminders import _fire_due

        async with SessionLocal() as db:
            u = await db.scalar(select(User).where(User.username == "demo"))
            before = await db.scalar(
                select(func.count()).select_from(Notification)
                .where(Notification.user_id == u.id)) or 0
            db.add(Reminder(user_id=u.id, title="桌面通知自检", detail="旅行当天提醒",
                            remind_at=datetime.now() - timedelta(minutes=1),
                            status="pending", source="trip", desktop=1))
            await db.commit()
        fired = await _fire_due()
        async with SessionLocal() as db:
            after = await db.scalar(
                select(func.count()).select_from(Notification)
                .where(Notification.user_id == u.id)) or 0
            row = await db.scalar(
                select(Notification).where(Notification.title == "桌面通知自检"))
        print(f"[desktop.fire] 触发 {fired} 条 | 新增站内通知 {after - before} 条 | 桌面分支命中 {bool(row)}")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
