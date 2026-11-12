"""按前端真实请求路径（Vite 代理 + session_id + 工具白名单）验证：
① 先规划 → ② 同会话再说「提醒我…」应走提醒分支 → ③ 通知接口可用。
"""
import json
import urllib.request
import uuid

PROXY = "http://127.0.0.1:5173"


def post(path, payload, token=None):
    req = urllib.request.Request(
        PROXY + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def stream(token, message, session_id=None):
    body = {"message": message, "request_id": uuid.uuid4().hex}
    if session_id:
        body["session_id"] = session_id
    req = urllib.request.Request(
        PROXY + "/api/agent/chat", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                 "Accept": "text/event-stream"})
    raw = urllib.request.urlopen(req, timeout=180).read().decode()
    out, ev = [], None
    for line in raw.splitlines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: ") and ev:
            out.append((ev, line[6:]))
    return out


token = post("/api/auth/login", {"username": "demo", "password": "demo123"})["data"]["access_token"]

# ① 规划（模拟前端默认「完全访问」= 不传 tools）
ev1 = stream(token, "我要去成都玩2天，预算1500元")
sid = json.loads(next(d for e, d in ev1 if e == "done"))["session_id"]
print("① 规划: plan_update=", "plan_update" in [e for e, _ in ev1], "| session:", sid)

# ② 同一会话里说提醒（这正是浏览器里失败的场景）
ev2 = stream(token, "提醒我明天早上8点出发去机场", session_id=sid)
kinds2 = [e for e, _ in ev2]
tools2 = [json.loads(d)["tool"] for e, d in ev2 if e == "tool_call"]
reply = "".join(json.loads(d)["text"] for e, d in ev2 if e == "token")
print("② 同会话提醒: tool_calls=", tools2)
print("   plan_update 出现? ->", "plan_update" in kinds2, "（应为 False）")
print("   回复原文:", reply.strip()[:120])

# ③ 通知接口
notif = post("/api/agent/notifications", {}, token) if False else json.loads(
    urllib.request.urlopen(urllib.request.Request(
        PROXY + "/api/agent/notifications",
        headers={"Authorization": f"Bearer {token}"}), timeout=30).read())["data"]
print("③ 通知: unread=", notif["unread"], "items=", len(notif["items"]))

assert "set_reminder" in tools2
assert "plan_update" not in kinds2
print("FRONTEND-PATH OK")
