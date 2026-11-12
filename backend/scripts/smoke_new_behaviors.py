"""冒烟：验证本轮修复的三个关键行为（真实服务）。"""
import json
import sys
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"


def call(path, payload, token=None, method="POST"):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method)
    return json.loads(urllib.request.urlopen(req, timeout=180).read())


def stream_chat(token, message):
    req = urllib.request.Request(
        BASE + "/api/agent/chat",
        data=json.dumps({"message": message, "request_id": uuid.uuid4().hex}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    raw = urllib.request.urlopen(req, timeout=180).read().decode()
    events = []
    ev = None
    for line in raw.splitlines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: ") and ev:
            events.append((ev, line[6:]))
    return events


token = call("/api/auth/login", {"username": "demo", "password": "demo123"})["data"]["access_token"]

# ① 只说目的地也要出行程（不再走 clarify 模板）
ev = stream_chat(token, "我想去西安玩")
kinds = [e for e, _ in ev]
draft = next((json.loads(d) for e, d in ev if e == "plan_update"), {})
done = next((json.loads(d) for e, d in ev if e == "done"), {})
print("① 目的地-only → plan_update:", "plan_update" in kinds,
      "| destination:", draft.get("destination"), "| days:", len(draft.get("day_list") or []),
      "| engine:", done.get("engine"), "| rag_hits:", done.get("rag_hits"))
assert "plan_update" in kinds and draft.get("destination") == "西安"

# ② 提醒工具
ev2 = stream_chat(token, "提醒我明天早上8点出发去机场")
tools2 = [json.loads(d)["tool"] for e, d in ev2 if e == "tool_call"]
print("② 提醒 → tool_calls:", tools2)
assert "set_reminder" in tools2

# ③ 提醒可查回
rems = call("/api/agent/reminders", None, token, "GET")["data"]
print("③ reminders:", [(r["title"], r["remind_at"], r["status"]) for r in rems[:3]])
assert rems

# ④ 通知接口
notif = call("/api/agent/notifications", None, token, "GET")["data"]
print("④ notifications unread:", notif["unread"], "count:", len(notif["items"]))
print("SMOKE-NEW OK")
