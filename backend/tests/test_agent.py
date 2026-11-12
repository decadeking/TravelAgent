"""Agent 对话链路单测：SSE 事件、澄清、降级、幂等。"""
from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.main import app


def _collect_events(client: TestClient, headers, message: str,
                    request_id: str | None = None, tools: list[str] | None = None):
    events: list[tuple[str, str]] = []
    rid = request_id or uuid.uuid4().hex
    body: dict = {"message": message, "request_id": rid}
    if tools is not None:
        body["tools"] = tools
    with client.stream("POST", "/api/agent/chat", headers=headers, json=body) as resp:
        assert resp.status_code == 200
        event = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event:
                events.append((event, line[6:]))
    return events, rid


def _login(client: TestClient) -> dict:
    r = client.post("/api/auth/login", json={"username": "demo", "password": "demo123"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def _login_admin(client: TestClient) -> dict:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def test_sse_chat_full_flow():
    with TestClient(app) as client:
        headers = _login(client)
        events, _ = _collect_events(
            client, headers, "我要去成都玩4天，预算3000元，带小孩，不想爬山")
        kinds = [e for e, _ in events]
        assert "tool_call" in kinds and "tool_result" in kinds
        assert "plan_update" in kinds and "done" in kinds

        draft = json.loads(next(d for e, d in events if e == "plan_update"))
        assert draft.get("degraded") is not True, "mock 正常路径不应降级"
        assert draft["destination"] == "成都"
        assert len(draft["day_list"]) == 4
        assert all(day["items"] for day in draft["day_list"])
        done = json.loads(next(d for e, d in events if e == "done"))
        assert done["session_id"]
        # 路径透明化：离线模拟必须如实标注（不得伪装成真实模型）
        assert done.get("engine") == "offline"
        assert done.get("model_used")
        # 幻觉治理：总结应带引用标注与「以实际为准」兜底话术
        tokens = "".join(json.loads(d)["text"] for e, d in events if e == "token")
        assert "以景区当日实际为准" in tokens


def test_clarify_when_slots_missing():
    with TestClient(app) as client:
        headers = _login(client)
        events, _ = _collect_events(client, headers, "帮我规划一次旅行吧")
        kinds = [e for e, _ in events]
        assert "plan_update" not in kinds          # 目的地未知，不生成行程
        tokens = "".join(json.loads(d)["text"] for e, d in events if e == "token")
        assert "目的地" in tokens or "城市" in tokens


def test_plan_with_destination_only():
    """只说目的地（没说天数/预算）也应正常规划，而不是走模板反问。"""
    with TestClient(app) as client:
        headers = _login_fresh(client)
        events, _ = _collect_events(client, headers, "我想去西安玩")
        kinds = [e for e, _ in events]
        assert "plan_update" in kinds and "done" in kinds
        draft = json.loads(next(d for e, d in events if e == "plan_update"))
        assert draft["destination"] == "西安"
        assert draft.get("degraded") is not True


def test_idempotent_replay():
    with TestClient(app) as client:
        headers = _login(client)
        _, rid = _collect_events(client, headers, "我要去杭州玩3天，预算5000元")
        events2, _ = _collect_events(client, headers, "我要去杭州玩3天，预算5000元", request_id=rid)
        done = json.loads(next(d for e, d in events2 if e == "done"))
        assert done["cached"] is True


def test_degrade_when_model_down():
    with TestClient(app) as client:
        headers = _login(client)
        admin = _login_admin(client)
        client.post("/api/admin/fault", json={"model_down": True}, headers=admin)
        try:
            events, _ = _collect_events(client, headers, "我要去上海玩2天，预算2000元")
            draft = json.loads(next(d for e, d in events if e == "plan_update"))
            assert draft.get("degraded") is True
        finally:
            client.post("/api/admin/fault", json={"reset": True}, headers=admin)


def test_models_endpoint():
    with TestClient(app) as client:
        headers = _login(client)
        data = client.get("/api/agent/models", headers=headers).json()["data"]
        ids = {m["id"] for m in data["models"]}
        assert "deepseek-v4-flash" in ids and "deepseek-4.1-flash" in ids
        assert data["default_model"]


def _login_fresh(client: TestClient) -> dict:
    """注册独立用户，避免与 demo 共享限流窗口造成串扰。"""
    name = f"u{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register",
                json={"username": name, "password": "secret123", "nickname": "测试"})
    r = client.post("/api/auth/login", json={"username": name, "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def test_tool_whitelist_limits_calls():
    """左下角选「仅天气」时，本次对话只应调用天气工具。"""
    with TestClient(app) as client:
        headers = _login_fresh(client)
        events, _ = _collect_events(client, headers, "我要去成都玩3天，预算2000元",
                                    tools=["get_weather"])
        called = {json.loads(d)["tool"] for e, d in events if e == "tool_call"}
        assert called == {"get_weather"}, f"实际调用：{called}"


def test_tool_whitelist_multiple():
    with TestClient(app) as client:
        headers = _login_fresh(client)
        events, _ = _collect_events(
            client, headers, "我要去杭州玩2天，预算1500元",
            tools=["get_weather", "search_poi", "estimate_budget"])
        called = {json.loads(d)["tool"] for e, d in events if e == "tool_call"}
        assert called <= {"get_weather", "search_poi", "estimate_budget"}
        assert "plan_route" not in called       # 未授权的工具不得被调用
