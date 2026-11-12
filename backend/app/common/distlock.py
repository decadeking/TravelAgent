"""分布式锁：SET NX EX + 看门狗续期 + Lua 比对释放。

场景：同一用户开两个标签页同时发起规划，两个任务写同一份行程，
数据互相覆盖、Token 重复计费。锁住「同一用户的规划」这一临界区。
"""
from __future__ import annotations

import asyncio
import uuid

from .config import settings
from .kvstore import get_kv


class DistributedLock:
    def __init__(self, key: str, ttl: int | None = None) -> None:
        self.key = key
        self.ttl = ttl or settings.plan_lock_ttl_seconds
        self.token = uuid.uuid4().hex
        self._watchdog: asyncio.Task | None = None

    async def acquire(self) -> bool:
        ok = await get_kv().acquire_lock(self.key, self.token, self.ttl)
        if ok:
            self._start_watchdog()
        return ok

    def _start_watchdog(self) -> None:
        async def _renew() -> None:
            interval = settings.plan_lock_watchdog_interval
            while True:
                await asyncio.sleep(interval)
                renewed = await get_kv().renew_lock(self.key, self.token, self.ttl)
                if not renewed:
                    break

        self._watchdog = asyncio.create_task(_renew())

    async def release(self) -> None:
        if self._watchdog:
            self._watchdog.cancel()
            self._watchdog = None
        await get_kv().release_lock(self.key, self.token)

    async def __aenter__(self) -> "DistributedLock":
        if not await self.acquire():
            raise LockBusyError(self.key)
        return self

    async def __aexit__(self, *exc) -> None:
        await self.release()


class LockBusyError(Exception):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__("已有规划任务进行中")


def plan_lock_key(user_id: int) -> str:
    return f"lock:plan:{user_id}"
