"""熔断器：每个下游（每个模型、每个工具）独立一个实例。

状态机：Closed →（窗口内失败率 ≥ 阈值且样本数足够）→ Open
        Open →（冷却后）→ HalfOpen →（探测全成）→ Closed / （探测失败）→ Open
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .config import settings
from .logging import get_logger

logger = get_logger("circuit_breaker")


@dataclass
class BreakerStats:
    total: int = 0
    failures: int = 0
    opened_at: float = 0.0
    half_open_probes: int = 0
    half_open_success: int = 0


class CircuitBreaker:
    """基于滑动统计窗口的熔断器。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.state = "closed"          # closed | open | half_open
        self._events: list[tuple[float, bool]] = []   # (时间戳, 是否失败)
        self._opened_at = 0.0
        self._half_open_probes = 0
        self._half_open_success = 0
        self._lock = None  # 简化：单进程下无需显式锁

    def _prune(self, now: float) -> None:
        window = settings.breaker_window_seconds
        self._events = [e for e in self._events if e[0] > now - window]

    def allow(self) -> bool:
        """是否放行本次请求。"""
        now = time.time()
        if self.state == "open":
            if now - self._opened_at >= settings.breaker_cooldown_seconds:
                self.state = "half_open"
                self._half_open_probes = 0
                self._half_open_success = 0
                logger.info("熔断器进入半开", breaker=self.name)
            else:
                return False
        if self.state == "half_open":
            if self._half_open_probes >= settings.breaker_half_open_probes:
                return False
            self._half_open_probes += 1
        return True

    def record(self, success: bool) -> None:
        now = time.time()
        if self.state == "half_open":
            if success:
                self._half_open_success += 1
                if self._half_open_success >= settings.breaker_half_open_probes:
                    self._reset()
                    logger.info("熔断器恢复为关闭", breaker=self.name)
            else:
                self._open(now)
            return

        self._events.append((now, not success))
        self._prune(now)
        total = len(self._events)
        if total < settings.breaker_min_samples:
            return
        failures = sum(1 for _, fail in self._events if fail)
        if failures / total >= settings.breaker_failure_threshold:
            self._open(now)

    def _open(self, now: float) -> None:
        self.state = "open"
        self._opened_at = now
        logger.warning("熔断器打开", breaker=self.name,
                       failure_rate=self._failure_rate())

    def _failure_rate(self) -> float:
        if not self._events:
            return 0.0
        return sum(1 for _, fail in self._events if fail) / len(self._events)

    def _reset(self) -> None:
        self.state = "closed"
        self._events.clear()
        self._half_open_probes = 0
        self._half_open_success = 0

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_rate": round(self._failure_rate(), 3),
            "samples": len(self._events),
        }


_registry: dict[str, CircuitBreaker] = {}


def get_breaker(name: str) -> CircuitBreaker:
    if name not in _registry:
        _registry[name] = CircuitBreaker(name)
    return _registry[name]


def all_breakers() -> list[dict]:
    return [b.snapshot() for b in _registry.values()]
