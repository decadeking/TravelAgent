"""cache-aside 缓存工具（Q38：一致性 + 穿透/击穿/雪崩三连）。

- 先读缓存，未命中回源并回填，写 TTL 时加 ±20% 随机抖动防雪崩；
- 穿透：回源为空也缓存「空值哨兵」，短 TTL，挡住对不存在数据的反复查询；
- 击穿：热点 key 过期瞬间用 SETNX 互斥重建，只放一个请求回源，其余短暂自旋读缓存；
- 命中率接入 metrics，骤降可告警（Q44）。

天气这类实时数据允许最多 1 小时不一致，因此 TTL 取 3600 秒。
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Awaitable, Callable

from .kvstore import get_kv
from .logging import get_logger
from .metrics import metrics

logger = get_logger("cache")

_EMPTY = "__empty__"          # 空值哨兵（防穿透）
_REBUILD_TTL = 10             # 互斥重建标记的 TTL


def _ttl_with_jitter(base: int) -> int:
    """TTL 加 ±20% 随机抖动，避免大量 key 同时过期（雪崩）。"""
    return max(5, int(base * random.uniform(0.8, 1.2)))


async def cached_get_or_build(
    key: str,
    builder: Callable[[], Awaitable[Any]],
    *,
    ttl: int = 3600,
    allow_empty: bool = True,
) -> Any:
    """cache-aside 读取：命中返回；未命中互斥回源并回填。"""
    kv = get_kv()
    raw = await kv.get(key)
    if raw is not None:
        metrics.inc("cache_hit_total")
        if raw == _EMPTY:
            return None
        try:
            return json.loads(raw)
        except Exception:
            pass
    metrics.inc("cache_miss_total")

    # 击穿防护：只放一个请求回源，其余等待后重读缓存
    lock_key = f"rebuild:{key}"
    got_lock = await kv.setnx(lock_key, "1", ex=_REBUILD_TTL)
    if not got_lock:
        for _ in range(20):                    # 最多等 2 秒
            await asyncio.sleep(0.1)
            raw = await kv.get(key)
            if raw is not None:
                metrics.inc("cache_hit_total")
                return None if raw == _EMPTY else json.loads(raw)
        # 等不到（持锁者失败）→ 自己回源兜底
    try:
        value = await builder()
    finally:
        if got_lock:
            await kv.delete(lock_key)
    if value is None or value == {} or (isinstance(value, dict) and not value.get("forecast")):
        if allow_empty:
            await kv.set(key, _EMPTY, ex=_ttl_with_jitter(60))   # 空值短 TTL
        return None
    await kv.set(key, json.dumps(value, ensure_ascii=False), ex=_ttl_with_jitter(ttl))
    return value


async def cache_invalidate(key: str) -> None:
    """写路径：先更新数据库，再删缓存（删不是改，防旧值覆盖新值）。"""
    await get_kv().delete(key)


def hit_rate() -> float:
    counters = metrics.snapshot().get("counters", {})
    hits = counters.get("cache_hit_total", 0)
    misses = counters.get("cache_miss_total", 0)
    total = hits + misses
    rate = round(hits / total, 4) if total else 0.0
    metrics.gauge("cache_hit_rate", rate)
    return rate
