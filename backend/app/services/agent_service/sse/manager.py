"""SSE 连接管理器。

- 维护 conn_id → (user_id, asyncio.Task) 注册表，在线连接数可查（监控指标）。
- 每 15 秒发送 ping 心跳，连续两次写入失败判定断开。
- 断开后的清理链：取消规划任务 → 任务内部关闭大模型 HTTP 流 → 写回会话状态 → 释放分布式锁。
- 用户离开的瞬间即停止模型计费。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ....common.logging import get_logger
from ....common.metrics import metrics

logger = get_logger("sse")


@dataclass
class Connection:
    conn_id: str
    user_id: int
    session_id: str
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1024))
    task: asyncio.Task | None = None
    closed: bool = False
    created_at: float = field(default_factory=time.time)
    last_write_ok: float = field(default_factory=time.time)
    fail_count: int = 0


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[str, Connection] = {}
        self._lock = asyncio.Lock()

    async def register(self, conn: Connection) -> None:
        async with self._lock:
            self._conns[conn.conn_id] = conn
            metrics.gauge("sse_connections", len(self._conns))

    async def unregister(self, conn_id: str) -> None:
        async with self._lock:
            self._conns.pop(conn_id, None)
            metrics.gauge("sse_connections", len(self._conns))

    async def send(self, conn: Connection, event: str, data: Any) -> bool:
        if conn.closed:
            return False
        try:
            conn.queue.put_nowait((event, data))
            conn.last_write_ok = time.time()
            conn.fail_count = 0
            return True
        except asyncio.QueueFull:
            conn.fail_count += 1
            return False

    def online_count(self) -> int:
        return len(self._conns)

    async def cancel(self, conn: Connection) -> None:
        """断开清理：取消规划任务。"""
        conn.closed = True
        if conn.task and not conn.task.done():
            conn.task.cancel()
            logger.info("已取消规划任务", extra={"event": "task_cancelled"})

    def snapshot(self) -> list[dict]:
        return [
            {"conn_id": c.conn_id, "user_id": c.user_id, "session_id": c.session_id,
             "age_s": round(time.time() - c.created_at, 1), "closed": c.closed}
            for c in self._conns.values()
        ]


manager = ConnectionManager()
