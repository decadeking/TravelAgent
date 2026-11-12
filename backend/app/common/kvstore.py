"""KV 存储抽象层：内存实现（默认）+ Redis 实现（可选）。

设计意图：把「限流 / 幂等 / 分布式锁 / 会话缓存」这些依赖 Redis 的能力
收敛到一个接口下。默认走进程内内存实现，保证零外部服务即可运行；
配置 KV_BACKEND=redis 时无缝切换到真实 Redis（生产形态）。
"""
from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from .config import settings


class KVStore(ABC):
    """键值存储统一接口。"""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]: ...

    @abstractmethod
    async def set(self, key: str, value: str, ex: int | None = None) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def setnx(self, key: str, value: str, ex: int | None = None) -> bool: ...

    @abstractmethod
    async def incrby(self, key: str, amount: int = 1, ex: int | None = None) -> int: ...

    @abstractmethod
    async def expire(self, key: str, seconds: int) -> None: ...

    @abstractmethod
    async def sliding_window_allow(
        self, key: str, limit: int, window: float, now: float | None = None
    ) -> tuple[bool, int, int]:
        """滑动窗口限流。返回 (是否放行, 剩余额度, 需等待秒数)。"""

    @abstractmethod
    async def acquire_lock(self, key: str, token: str, ttl: int) -> bool: ...

    @abstractmethod
    async def release_lock(self, key: str, token: str) -> bool: ...

    @abstractmethod
    async def renew_lock(self, key: str, token: str, ttl: int) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...

    # ---- JSON 便捷方法 ----
    async def get_json(self, key: str) -> Any:
        raw = await self.get(key)
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value: Any, ex: int | None = None) -> None:
        await self.set(key, json.dumps(value, ensure_ascii=False), ex=ex)


class MemoryKVStore(KVStore):
    """进程内 KV 实现，带 TTL、SETNX、有序集合（滑动窗口）与锁语义。"""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._lock = asyncio.Lock()

    # --- 内部 ---
    def _alive(self, key: str, now: float) -> bool:
        item = self._data.get(key)
        if item is None:
            return False
        _, exp = item
        if exp is not None and exp <= now:
            self._data.pop(key, None)
            return False
        return True

    async def get(self, key: str) -> Optional[str]:
        now = time.time()
        async with self._lock:
            if not self._alive(key, now):
                return None
            return self._data[key][0]

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        exp = time.time() + ex if ex else None
        async with self._lock:
            self._data[key] = (value, exp)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)
            self._zsets.pop(key, None)

    async def setnx(self, key: str, value: str, ex: int | None = None) -> bool:
        now = time.time()
        async with self._lock:
            if self._alive(key, now):
                return False
            self._data[key] = (value, now + ex if ex else None)
            return True

    async def incrby(self, key: str, amount: int = 1, ex: int | None = None) -> int:
        now = time.time()
        async with self._lock:
            if self._alive(key, now):
                val = int(self._data[key][0]) + amount
                cur_exp = self._data[key][1]
                self._data[key] = (str(val), cur_exp)
            else:
                val = amount
                self._data[key] = (str(val), now + ex if ex else None)
            return val

    async def expire(self, key: str, seconds: int) -> None:
        async with self._lock:
            if key in self._data:
                self._data[key] = (self._data[key][0], time.time() + seconds)

    async def sliding_window_allow(
        self, key: str, limit: int, window: float, now: float | None = None
    ) -> tuple[bool, int, int]:
        now = now if now is not None else time.time()
        async with self._lock:
            ts_list = [t for t in self._zsets.get(key, {}).values() if t > now - window]
            if len(ts_list) < limit:
                member = f"{now:.6f}-{len(ts_list)}"
                bucket = self._zsets.setdefault(key, {})
                bucket[member] = now
                return True, limit - len(ts_list) - 1, 0
            oldest = min(ts_list)
            retry_after = max(1, int(oldest + window - now) + 1)
            return False, 0, retry_after

    # 锁
    async def acquire_lock(self, key: str, token: str, ttl: int) -> bool:
        return await self.setnx(key, token, ex=ttl)

    async def release_lock(self, key: str, token: str) -> bool:
        async with self._lock:
            item = self._data.get(key)
            if item and item[0] == token:
                self._data.pop(key, None)
                return True
            return False

    async def renew_lock(self, key: str, token: str, ttl: int) -> bool:
        async with self._lock:
            item = self._data.get(key)
            if item and item[0] == token:
                self._data[key] = (token, time.time() + ttl)
                return True
            return False

    async def close(self) -> None:
        self._data.clear()
        self._zsets.clear()


# Redis 滑动窗口 Lua 脚本（原子执行，避免竞态）
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, ARGV[4])
    redis.call('EXPIRE', key, math.ceil(window))
    return {1, limit - count - 1, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local wait = 1
    if oldest[2] then
        wait = math.ceil(tonumber(oldest[2]) + window - now) + 1
    end
    return {0, 0, wait}
end
"""

_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

_RENEW_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
else
    return 0
end
"""


class RedisKVStore(KVStore):
    """真实 Redis 实现（生产形态）。"""

    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Optional[str]:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        await self._redis.set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def setnx(self, key: str, value: str, ex: int | None = None) -> bool:
        return bool(await self._redis.set(key, value, nx=True, ex=ex))

    async def incrby(self, key: str, amount: int = 1, ex: int | None = None) -> int:
        val = await self._redis.incrby(key, amount)
        if ex:
            await self._redis.expire(key, ex)
        return int(val)

    async def expire(self, key: str, seconds: int) -> None:
        await self._redis.expire(key, seconds)

    async def sliding_window_allow(
        self, key: str, limit: int, window: float, now: float | None = None
    ) -> tuple[bool, int, int]:
        now = now if now is not None else time.time()
        member = f"{now:.6f}"
        res = await self._redis.eval(
            _SLIDING_WINDOW_LUA, 1, key, now, window, limit, member
        )
        return bool(res[0]), int(res[1]), int(res[2])

    async def acquire_lock(self, key: str, token: str, ttl: int) -> bool:
        return bool(await self._redis.set(key, token, nx=True, ex=ttl))

    async def release_lock(self, key: str, token: str) -> bool:
        return bool(await self._redis.eval(_RELEASE_LOCK_LUA, 1, key, token))

    async def renew_lock(self, key: str, token: str, ttl: int) -> bool:
        return bool(await self._redis.eval(_RENEW_LOCK_LUA, 1, key, token, ttl))

    async def close(self) -> None:
        await self._redis.aclose()


_kv: KVStore | None = None


def get_kv() -> KVStore:
    """获取全局 KV 单例。"""
    global _kv
    if _kv is None:
        if settings.kv_backend == "redis":
            try:
                _kv = RedisKVStore(settings.redis_url)
            except Exception:  # pragma: no cover - 降级到内存
                _kv = MemoryKVStore()
        else:
            _kv = MemoryKVStore()
    return _kv


async def close_kv() -> None:
    global _kv
    if _kv is not None:
        await _kv.close()
        _kv = None
