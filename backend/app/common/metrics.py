"""轻量指标注册表 + Prometheus 文本导出。

覆盖：QPS、P95 时延、大模型成功率、每小时 token 消耗、
熔断器状态、SSE 在线连接数、缓存命中率。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._gauges: dict[str, float] = {}
        self._tokens_by_hour: dict[str, int] = defaultdict(int)

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, ms: float) -> None:
        with self._lock:
            bucket = self._latencies[name]
            bucket.append(ms)
            if len(bucket) > 5000:
                del bucket[:2500]

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def add_tokens(self, count: int) -> None:
        hour = time.strftime("%Y-%m-%dT%H")
        with self._lock:
            self._tokens_by_hour[hour] += count

    def tokens_last_hour(self) -> int:
        hour = time.strftime("%Y-%m-%dT%H")
        with self._lock:
            return self._tokens_by_hour.get(hour, 0)

    def percentile(self, name: str, p: float) -> float:
        with self._lock:
            data = sorted(self._latencies.get(name, []))
        if not data:
            return 0.0
        idx = min(len(data) - 1, int(len(data) * p))
        return round(data[idx], 2)

    def snapshot(self) -> dict:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            lat = {k: len(v) for k, v in self._latencies.items()}
        return {
            "counters": counters,
            "gauges": gauges,
            "latency_samples": lat,
            "p95": {k: self.percentile(k, 0.95) for k in lat},
            "tokens_last_hour": self.tokens_last_hour(),
        }

    def to_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
        for k, v in counters.items():
            lines.append(f"# TYPE ta_{k} counter")
            lines.append(f"ta_{k} {v}")
        for k, v in gauges.items():
            lines.append(f"# TYPE ta_{k} gauge")
            lines.append(f"ta_{k} {v}")
        for k in list(counters) + list(self._latencies):
            p95 = self.percentile(k.replace("_total", ""), 0.95)
            if p95:
                lines.append(f"# TYPE ta_{k}_p95 gauge")
                lines.append(f"ta_{k}_p95 {p95}")
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()
