"""稳定性机制单测：限流 / 熔断 / 幂等 / 分布式锁 / 有限重试。"""
from __future__ import annotations

import pytest

from app.common.circuit_breaker import CircuitBreaker
from app.common.config import settings
from app.common.distlock import DistributedLock
from app.common.idempotency import IdemState, IdempotencyGuard
from app.common.kvstore import MemoryKVStore
from app.common.resilience import TransientError, call_with_resilience


async def test_sliding_window_rate_limit():
    kv = MemoryKVStore()
    limit = 5
    allowed = 0
    for _ in range(8):
        ok, remaining, retry_after = await kv.sliding_window_allow("k", limit, 60.0)
        if ok:
            allowed += 1
    assert allowed == limit          # 前 5 次放行
    ok, _, retry_after = await kv.sliding_window_allow("k", limit, 60.0)
    assert ok is False and retry_after > 0


async def test_setnx_and_ttl():
    kv = MemoryKVStore()
    assert await kv.setnx("a", "1", ex=60) is True
    assert await kv.setnx("a", "2", ex=60) is False
    assert await kv.get("a") == "1"
    assert await kv.incrby("c", 3) == 3
    assert await kv.incrby("c", 2) == 5


async def test_circuit_breaker_opens_and_recovers():
    cb = CircuitBreaker("test")
    # 前 5 次失败达到最小样本数，失败率 100% → 打开
    for _ in range(settings.breaker_min_samples):
        assert cb.allow() is True
        cb.record(False)
    assert cb.state == "open"
    assert cb.allow() is False       # 冷却期内快速失败

    # 模拟冷却结束 → 半开 → 探测全部成功 → 关闭
    cb._opened_at = 0
    for _ in range(settings.breaker_half_open_probes):
        assert cb.allow() is True
        cb.record(True)
    assert cb.state == "closed"


async def test_idempotency_flow():
    guard = IdempotencyGuard()
    rid = "req-123"
    assert (await guard.begin(rid)).state == IdemState.NEW
    assert (await guard.begin(rid)).state == IdemState.IN_PROGRESS
    await guard.complete(rid, {"plan": "ok"})
    done = await guard.begin(rid)
    assert done.state == IdemState.DONE
    assert done.result == {"plan": "ok"}


async def test_distributed_lock_exclusive():
    lock1 = DistributedLock("lock:u1")
    lock2 = DistributedLock("lock:u1")
    assert await lock1.acquire() is True
    assert await lock2.acquire() is False     # 同一用户互斥
    await lock1.release()
    assert await lock2.acquire() is True
    await lock2.release()


async def test_retry_then_success(monkeypatch):
    monkeypatch.setattr(settings, "retry_base_delay", 0.01)
    monkeypatch.setattr(settings, "retry_max_attempts", 2)
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("瞬时错误")
        return "ok"

    result = await call_with_resilience(flaky, downstream="test", timeout=5)
    assert result == "ok"
    assert calls["n"] == 3        # 失败两次后成功


async def test_business_error_not_retried():
    calls = {"n": 0}

    async def bad():
        calls["n"] += 1
        raise ValueError("参数错误")

    with pytest.raises(ValueError):
        await call_with_resilience(bad, downstream="test", timeout=5)
    assert calls["n"] == 1        # 业务错误不重试
