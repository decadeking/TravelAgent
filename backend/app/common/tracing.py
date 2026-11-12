"""轻量链路追踪（进程内 Span 记录器）。

真实生产用 OpenTelemetry SDK + Jaeger；这里实现同构的轻量版本，
让「网关 → agent-service → 大模型 → 工具」整条链路可在一个 trace_id
下查看，答辩/演示时 /api/admin/traces 可直接看到。
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from typing import Any

from . import context


class Span:
    def __init__(self, name: str, trace_id: str, parent_id: str | None) -> None:
        self.name = name
        self.trace_id = trace_id
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_id = parent_id
        self.start = time.perf_counter()
        self.duration_ms = 0.0
        self.attributes: dict[str, Any] = {}
        self.status = "ok"

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "attributes": self.attributes,
            "start": self.start,
        }


class Tracer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spans: deque[Span] = deque(maxlen=2000)

    @contextmanager
    def span(self, name: str, **attributes: Any):
        trace_id = context.get_trace_id() or "no-trace"
        s = Span(name, trace_id, None)
        s.attributes.update(attributes)
        try:
            yield s
        except Exception as exc:
            s.status = "error"
            s.attributes["error"] = str(exc)
            raise
        finally:
            s.duration_ms = (time.perf_counter() - s.start) * 1000
            with self._lock:
                self._spans.append(s)

    def recent(self, trace_id: str | None = None, limit: int = 100) -> list[dict]:
        with self._lock:
            spans = list(self._spans)
        if trace_id:
            spans = [s for s in spans if s.trace_id == trace_id]
        return [s.to_dict() for s in spans[-limit:]]

    def traces(self, limit: int = 30) -> list[dict]:
        with self._lock:
            spans = list(self._spans)
        grouped: dict[str, list[dict]] = {}
        for s in spans:
            grouped.setdefault(s.trace_id, []).append(s.to_dict())
        out = [
            {"trace_id": tid, "span_count": len(v),
             "total_ms": round(sum(x["duration_ms"] for x in v), 2), "spans": v}
            for tid, v in grouped.items()
        ]
        out.sort(key=lambda x: -(x["spans"][0]["start"] if x["spans"] else 0))
        return out[:limit]


tracer = Tracer()
