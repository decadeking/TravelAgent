"""新增工具与安全存储：当前时间工具 / 行程提醒工具 / 密钥加密。"""
from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.main import app


def _collect_events(client: TestClient, headers, message: str,
                    session_id: str | None = None):
    events: list[tuple[str, str]] = []
    rid = uuid.uuid4().hex
    body: dict = {"message": message, "request_id": rid}
    if session_id:
        body["session_id"] = session_id
    with client.stream("POST", "/api/agent/chat", headers=headers,
                       json=body) as resp:
        assert resp.status_code == 200
        event = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event:
                events.append((event, line[6:]))
    return events, rid


def _login_fresh(client: TestClient) -> dict:
    name = f"u{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register",
                json={"username": name, "password": "secret123", "nickname": "测试"})
    r = client.post("/api/auth/login", json={"username": name, "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def test_current_time_tool_is_real():
    from app.services.tool_service import tools
    res = tools.get_current_time("成都")
    assert res["source"] == "server-clock"
    assert len(res["date"]) == 10 and ":" in res["time"]


def test_parse_remind_at_variants():
    from datetime import datetime
    from app.services.agent_service.reminders import parse_remind_at
    now = datetime(2026, 10, 14, 10, 0)
    assert parse_remind_at("明天早上8点", now=now).hour == 8
    assert parse_remind_at("明天早上8点", now=now).day == 15
    assert parse_remind_at("3天后", now=now).day == 17
    assert parse_remind_at("2026-12-01 09:30", now=now).minute == 30


def test_reminder_tool_creates_reminder():
    """智能体识别到「提醒我…」应调用 set_reminder 并落库，接口可查回。"""
    with TestClient(app) as client:
        headers = _login_fresh(client)
        events, _ = _collect_events(client, headers, "提醒我明天早上8点出发去机场")
        called = {json.loads(d)["tool"] for e, d in events if e == "tool_call"}
        assert "set_reminder" in called
        rows = client.get("/api/agent/reminders", headers=headers).json()["data"]
        assert rows and rows[0]["title"]
        assert rows[0]["status"] == "pending"


def test_reminder_api_and_notifications():
    with TestClient(app) as client:
        headers = _login_fresh(client)
        r = client.post("/api/agent/reminders", headers=headers,
                        json={"title": "测试提醒", "when": "1天后"}).json()["data"]
        assert r["reminder_id"]
        notif = client.get("/api/agent/notifications", headers=headers).json()["data"]
        assert "unread" in notif


def test_reminder_after_planning_in_same_session():
    """同一会话里先规划行程、再说「提醒我…」，仍应走提醒分支（不被历史槽位带走）。"""
    with TestClient(app) as client:
        headers = _login_fresh(client)
        events, _ = _collect_events(client, headers, "我要去成都玩2天，预算1500元")
        sid = json.loads(next(d for e, d in events if e == "done"))["session_id"]
        events2, _ = _collect_events(client, headers, "提醒我后天早上7点出发",
                                     session_id=sid)
        tools = [json.loads(d)["tool"] for e, d in events2 if e == "tool_call"]
        assert "set_reminder" in tools, f"应调用 set_reminder，实际 {tools}"
        assert "plan_update" not in [e for e, _ in events2], "提醒请求不应再生成行程"


def test_api_key_encrypted_at_rest():
    """密钥必须以密文落库，且能正确解回明文。"""
    from app.common.crypto import decrypt_secret, encrypt_secret, is_encrypted
    raw = "sk-abcdef1234567890abcdef1234567890"
    enc = encrypt_secret(raw)
    assert is_encrypted(enc) and raw not in enc
    assert decrypt_secret(enc) == raw
    # 历史明文兼容
    assert decrypt_secret(raw) == raw
