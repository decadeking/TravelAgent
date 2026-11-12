"""冒烟：登录→SSE 对话→断言事件带 id 序号、无静默降级。"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, payload, token=None):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


login = post("/api/auth/login", {"username": "demo", "password": "demo123"})
token = login["data"]["access_token"]

req = urllib.request.Request(
    BASE + "/api/agent/chat",
    data=json.dumps({"message": "我要去成都玩3天，预算2500元",
                     "request_id": "smoke-001"}).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
resp = urllib.request.urlopen(req, timeout=120)
raw = resp.read().decode()

events = []
event, evid = None, None
for line in raw.splitlines():
    if line.startswith("id: "):
        evid = line[4:]
    elif line.startswith("event: "):
        event = line[7:]
    elif line.startswith("data: ") and event:
        events.append((event, evid, line[6:]))
        evid = None

kinds = [e for e, _, _ in events]
print("event kinds:", sorted(set(kinds)))
ids = [i for _, i, _ in events if i]
print("numbered events:", len(ids), "first/last:", ids[0] if ids else None, ids[-1] if ids else None)
draft = next(json.loads(d) for e, _, d in events if e == "plan_update")
print("degraded:", draft.get("degraded"), "| destination:", draft.get("destination"),
      "| days:", draft.get("days"), "| citations:", len(draft.get("citations") or []))
tokens = "".join(json.loads(d)["text"] for e, _, d in events if e == "token")
print("has fallback phrase:", "以景区当日实际为准" in tokens)
assert "plan_update" in kinds and "done" in kinds
assert draft.get("degraded") is not True, "真实链路不应降级"
assert ids, "SSE 事件应带编号"
print("SMOKE OK")
