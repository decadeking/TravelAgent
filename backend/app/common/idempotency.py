"""幂等机制：request_id + Redis SETNX 占位。

- 首次请求：占位并执行，完成后缓存结果（TTL 10 分钟）。
- 相同 request_id 再次到达：已完成返回缓存结果，进行中返回「处理中」。
  大模型绝不会被同一请求调用两次。
- 顺带解决「SSE 断开后用户疯狂点重试」的经典场景。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .config import settings
from .kvstore import get_kv
from .logging import get_logger

logger = get_logger("idempotency")


class IdemState(str, Enum):
    NEW = "new"            # 首次，可以执行
    IN_PROGRESS = "in_progress"
    DONE = "done"


@dataclass
class IdemResult:
    state: IdemState
    result: Any = None


class IdempotencyGuard:
    def __init__(self, namespace: str = "idem") -> None:
        self.ns = namespace

    def _key(self, request_id: str) -> str:
        return f"{self.ns}:{request_id}"

    async def begin(self, request_id: str) -> IdemResult:
        """尝试占位。

        Redis 故障时选择「放行 + 告警」——幂等是增强能力，可用性优先，
        数据库层的 request_id 唯一索引做最后兜底（Q32）。
        """
        kv = get_kv()
        try:
            existing = await kv.get(self._key(request_id))
            if existing is None:
                ok = await kv.setnx(self._key(request_id), "processing",
                                    ex=settings.idempotency_ttl_seconds)
                if ok:
                    return IdemResult(IdemState.NEW)
                existing = await kv.get(self._key(request_id))
            if existing == "processing":
                return IdemResult(IdemState.IN_PROGRESS)
            # 已完成，取出缓存结果
            cached = await kv.get(f"{self.ns}:result:{request_id}")
            try:
                import json
                result = json.loads(cached) if cached else None
            except Exception:
                result = None
            return IdemResult(IdemState.DONE, result)
        except Exception as exc:
            logger.warning("幂等存储不可用，放行请求（DB 唯一索引兜底）: %s", exc)
            return IdemResult(IdemState.NEW)

    async def complete(self, request_id: str, result: Any) -> None:
        import json
        try:
            kv = get_kv()
            await kv.set(self._key(request_id), "done", ex=settings.idempotency_ttl_seconds)
            await kv.set(f"{self.ns}:result:{request_id}",
                         json.dumps(result, ensure_ascii=False),
                         ex=settings.idempotency_ttl_seconds)
        except Exception as exc:
            logger.warning("幂等结果写入失败（不影响主流程）: %s", exc)

    async def fail(self, request_id: str) -> None:
        """执行失败则释放占位，允许用户重试。"""
        try:
            await get_kv().delete(self._key(request_id))
        except Exception:
            pass
