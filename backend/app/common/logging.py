"""结构化日志：JSON 输出，每条携带 trace_id / session_id / user_id。

对应设计中的可观测性：日志可检索、可聚合。默认同时输出到控制台。
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from . import context


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": context.get_trace_id(),
        }
        uid = context.get_user_id()
        if uid is not None:
            payload["user_id"] = uid
        sid = context.get_session_id()
        if sid:
            payload["session_id"] = sid
        # 结构化附加字段
        for key in ("breaker", "tool", "model", "latency_ms", "tokens", "event"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger("travelagent")
    root.setLevel(logging.INFO)
    # MCP server 走 stdio 传输，stdout 属于协议帧，日志必须改道 stderr，
    # 否则日志会混入 JSON-RPC 流导致报文解析失败。
    stream = sys.stderr if os.environ.get("LOG_TO_STDERR") == "1" else sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.propagate = False
    _configured = True


_STD_KEYS = {"exc_info", "stack_info", "stacklevel", "extra", "msg", "args"}


class _LoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.update(self.extra)
        # 把自定义字段（如 downstream/tool/breaker）统一收进 extra，避免
        # logging 误当作 _log 的关键字参数而报错
        for key in [k for k in list(kwargs) if k not in _STD_KEYS]:
            extra[key] = kwargs.pop(key)
        return msg, kwargs


def get_logger(name: str) -> logging.LoggerAdapter:
    _configure()
    return _LoggerAdapter(logging.getLogger(f"travelagent.{name}"), {})
