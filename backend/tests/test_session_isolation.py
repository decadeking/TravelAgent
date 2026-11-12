"""会话上下文隔离 + 图片多模态链路回归。

对应修复：
- 多用户共用一个上下文的 bug：chat 接口对传入 session_id 校验归属；
  新建 session_id 加随机数字后缀保证跨用户全局唯一；
  Redis 会话上下文持久化 user_id，恢复接口按归属过滤。
- 上传图片模型可见：/api/media/{id} 引用转 base64 data URL，
  以 OpenAI 兼容 image_url 多模态格式挂到最后一条用户消息。
"""
from __future__ import annotations

import base64
import json
import re
import uuid

from app.db.session import SessionLocal
from app.services.agent_service.llm.adapter import _with_images
from app.services.agent_service.service import _collect_images


def _sse_events(text: str) -> dict[str, str]:
    """把 SSE 响应体解析为 {事件名: 最后一个 data}（同名事件以最后一条为准）。"""
    out: dict[str, str] = {}
    event = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: ") and event:
            out[event] = line[6:]
    return out

# 1x1 透明 PNG（测试用最小合法图片）
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


async def _login(client, username: str) -> dict:
    r = await client.post("/api/auth/login",
                          json={"username": username, "password": "demo123"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _chat_once(client, headers: dict, message: str,
                     session_id: str | None = None) -> tuple[int, dict]:
    body = {"message": message, "request_id": uuid.uuid4().hex}
    if session_id:
        body["session_id"] = session_id
    r = await client.post("/api/agent/chat", headers=headers, json=body)
    events = _sse_events(r.text)
    return r.status_code, (json.loads(events["done"]) if "done" in events else {})


async def test_session_id_format_and_uniqueness(client):
    """新建会话 id 保持「s+纯数字」命名规范，且两次新建不撞号（跨用户隔离第一道防线）。"""
    a = await _login(client, "demo")
    b = await _login(client, "chengzi")
    _, done_a = await _chat_once(client, a, "去成都玩3天，预算2000元")
    _, done_b = await _chat_once(client, b, "去重庆玩2天，预算1500元")
    sid_a, sid_b = done_a["session_id"], done_b["session_id"]
    assert re.fullmatch(r"s\d{13}", sid_a), f"会话名应为 s+纯数字: {sid_a}"
    assert sid_a != sid_b, "不同用户新建会话不得撞号共用上下文"


async def test_cross_user_session_access_forbidden(client):
    """他人会话：续聊被 403 拒绝，状态读取按归属过滤（修复串上下文 bug）。"""
    a = await _login(client, "demo")
    b = await _login(client, "chengzi")
    _, done = await _chat_once(client, a, "去杭州玩2天，预算1000元")
    sid = done["session_id"]

    # B 拿 A 的 session_id 续聊 → 403，且不会写入 A 的上下文
    status, _ = await _chat_once(client, b, "帮我改成3天", session_id=sid)
    assert status == 403, f"跨用户续聊应 403，实际 {status}"

    # B 读 A 的会话状态 → data 为 None；A 自己读 → 正常
    rb = await client.get(f"/api/agent/sessions/{sid}", headers=b)
    assert rb.json()["data"] is None, "他人不得读取会话上下文"
    ra = await client.get(f"/api/agent/sessions/{sid}", headers=a)
    assert ra.json()["data"], "本人应能恢复自己的会话"


async def test_uploaded_image_becomes_data_url(client, auth_headers):
    """上传图片后：/api/media/{id} 引用能转成 base64 data URL（模型可见的前提）。"""
    up = await client.post("/api/media/upload", headers=auth_headers,
                           params={"kind": "image"},
                           files={"file": ("iso_test.png", _PNG_1X1, "image/png")})
    assert up.status_code == 200
    media_id = up.json()["data"]["id"]

    async with SessionLocal() as db:
        urls = await _collect_images(db, f"看看这张图 【图片】/api/media/{media_id}")
    assert len(urls) == 1 and urls[0].startswith("data:image/png;base64,")
    # data URL 能解码回原始字节 → 文件本体确实被读进来了，不是路径字符串
    assert base64.b64decode(urls[0].split(",", 1)[1]) == _PNG_1X1

    # 不存在的引用安全忽略，不炸链路
    async with SessionLocal() as db:
        assert await _collect_images(db, "【图片】/api/media/999999") == []


def test_adapter_builds_multimodal_message():
    """adapter 把图片挂到最后一条用户消息（OpenAI 兼容 image_url 格式）。"""
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "第一轮"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "看这张图"}]
    out = _with_images(msgs, ["data:image/png;base64,QUJD"])
    assert out[1]["content"] == "第一轮"          # 历史消息不动
    last = out[-1]["content"]
    assert isinstance(last, list) and last[0]["type"] == "text"
    assert last[1] == {"type": "image_url",
                       "image_url": {"url": "data:image/png;base64,QUJD"}}
    # 无图片时原样返回
    assert _with_images(msgs, None) is msgs


async def test_chat_with_image_reference_offline_ok(client, auth_headers):
    """离线 mock 下带图片引用发消息：全链路不报错，正常产出行程。"""
    up = await client.post("/api/media/upload", headers=auth_headers,
                           params={"kind": "image"},
                           files={"file": ("iso_test2.png", _PNG_1X1, "image/png")})
    media_id = up.json()["data"]["id"]
    status, done = await _chat_once(
        client, auth_headers, f"参考这张图规划 【图片】/api/media/{media_id}，去西安玩2天预算1000")
    assert status == 200 and done.get("session_id")
