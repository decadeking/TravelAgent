"""限流：双层设计。

- 网关层：Redis + Lua 滑动窗口（单用户每分钟 N 次、全局 QPS 上限），
  超限返回 429 + Retry-After。
- 服务层：asyncio.Semaphore 把大模型并发压到阈值以内。
"""
from __future__ import annotations

import asyncio

from .config import settings
from .errors import RateLimitError
from .kvstore import get_kv


async def check_user_rate_limit(user_id: int) -> tuple[int, int]:
    """单用户滑动窗口限流。返回 (剩余额度, 重置秒数)。"""
    kv = get_kv()
    allowed, remaining, retry_after = await kv.sliding_window_allow(
        f"rl:user:{user_id}", settings.rate_limit_per_user_per_minute, 60.0
    )
    if not allowed:
        raise RateLimitError(retry_after=retry_after)
    return remaining, retry_after


async def check_global_rate_limit() -> None:
    """全局 QPS 限流。"""
    kv = get_kv()
    allowed, _, retry_after = await kv.sliding_window_allow(
        "rl:global", settings.rate_limit_global_qps, 1.0
    )
    if not allowed:
        raise RateLimitError(retry_after=retry_after or 1,
                             message="系统繁忙，请稍后重试")


class LLMConcurrencyLimiter:
    """服务层大模型并发信号量。"""

    def __init__(self, limit: int | None = None) -> None:
        self._sem = asyncio.Semaphore(limit or settings.llm_max_concurrency)

    async def __aenter__(self):
        await self._sem.acquire()
        return self

    async def __aexit__(self, *exc):
        self._sem.release()


llm_limiter = LLMConcurrencyLimiter()
