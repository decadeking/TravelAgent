"""请求级协程上下文（contextvars）。

对应设计中「网关注入 trace_id / user_id，下游信任上下文」的思想：
- trace_id 贯穿网关 → 服务 → LLM/工具调用全链路
- user_id 由网关鉴权后注入，下游不再重复解析 token
contextvars 绑定到「当前协程任务」，协程切换时自动跟随、协程间互相隔离。
"""
from __future__ import annotations

import contextvars
import uuid

_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("user_id", default=None)
_username: contextvars.ContextVar[str] = contextvars.ContextVar("username", default="")
_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def parse_traceparent(header: str | None) -> str | None:
    """解析 W3C traceparent：00-{32hex trace_id}-{16hex span_id}-{flags}。"""
    if not header:
        return None
    parts = header.strip().split("-")
    if len(parts) == 4 and len(parts[1]) == 32 and all(c in "0123456789abcdef" for c in parts[1]):
        return parts[1]
    return None


def make_traceparent(trace_id: str) -> str:
    span_id = uuid.uuid4().hex[:16]
    return f"00-{trace_id}-{span_id}-01"


def set_trace_id(value: str | None = None) -> str:
    tid = value or new_trace_id()
    _trace_id.set(tid)
    return tid


def get_trace_id() -> str:
    return _trace_id.get()


def set_user(user_id: int | None, username: str = "") -> None:
    _user_id.set(user_id)
    _username.set(username)


def get_user_id() -> int | None:
    return _user_id.get()


def get_username() -> str:
    return _username.get()


def set_session_id(value: str) -> None:
    _session_id.set(value)


def get_session_id() -> str:
    return _session_id.get()
