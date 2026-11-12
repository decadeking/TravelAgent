"""韧性组件：有限重试 + 超时控制 + 熔断联动。

- 只重试瞬时错误（超时 / 429 / 5xx）；业务错误（参数校验失败）永不重试。
- 指数退避 + 随机抖动，避免重试风暴。
- 与熔断器联动：熔断打开时快速失败，不排队。
"""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

from .circuit_breaker import get_breaker
from .config import settings
from .errors import UpstreamError
from .logging import get_logger

logger = get_logger("resilience")
T = TypeVar("T")


class TransientError(Exception):
    """可重试的瞬时错误（超时 / 429 / 5xx）。"""


async def call_with_resilience(
    func: Callable[[], Awaitable[T]],
    *,
    downstream: str,
    timeout: float | None = None,
    fallback: Callable[[], Awaitable[T]] | None = None,
) -> T:
    """带熔断 + 超时 + 有限重试的调用包装。

    :param downstream: 下游名称（每个下游一个独立熔断器）
    :param timeout: 单次调用超时（秒）
    :param fallback: 降级函数（熔断打开或重试耗尽时调用）
    """
    breaker = get_breaker(downstream)
    if not breaker.allow():
        logger.warning("熔断打开，快速失败", breaker=downstream)
        if fallback:
            return await fallback()
        raise UpstreamError(f"{downstream} 暂时不可用（熔断打开）")

    attempts = settings.retry_max_attempts + 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            coro = func()
            result = await (asyncio.wait_for(coro, timeout) if timeout else coro)
            breaker.record(True)
            return result
        except (asyncio.TimeoutError, TransientError) as exc:
            breaker.record(False)
            last_exc = exc
        except Exception as exc:  # 业务错误：不重试，但计一次失败
            breaker.record(False)
            raise
        if attempt < attempts - 1:
            delay = settings.retry_base_delay * (2 ** attempt)
            jitter = delay * settings.retry_jitter
            delay += random.uniform(-jitter, jitter)
            logger.info("重试请求", downstream=downstream, attempt=attempt + 1,
                        delay=round(delay, 3))
            await asyncio.sleep(max(0.0, delay))

    logger.error("重试耗尽", downstream=downstream)
    if fallback:
        return await fallback()
    raise UpstreamError(f"{downstream} 调用失败：{last_exc}")


async def with_timeout(coro: Awaitable[T], timeout: float) -> T:
    return await asyncio.wait_for(coro, timeout)
