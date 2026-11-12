"""故障演练（Q34）：幂等并发重放——同一 request_id 10 个并发请求，
只有 1 个能拿到 NEW 占位，其余为 IN_PROGRESS/DONE，大模型绝不会被重复调用。"""
from __future__ import annotations

import asyncio

from app.common.idempotency import IdempotencyGuard, IdemState


async def test_concurrent_replay_only_one_new():
    rid = "req-concurrent-001"
    guard = IdempotencyGuard()

    async def _begin():
        return await guard.begin(rid)

    results = await asyncio.gather(*[_begin() for _ in range(10)])
    new_count = sum(1 for r in results if r.state == IdemState.NEW)
    assert new_count == 1, f"应恰好 1 个 NEW，实际 {new_count}"
    assert all(r.state in (IdemState.NEW, IdemState.IN_PROGRESS) for r in results)

    # 完成后重放：返回缓存结果，不再执行
    await guard.complete(rid, {"plan": "cached"})
    replay = await guard.begin(rid)
    assert replay.state == IdemState.DONE
    assert replay.result == {"plan": "cached"}
