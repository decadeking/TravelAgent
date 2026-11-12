"""Token 用量配额：按用户每日配额，调用前查 KV 计数，超额拒绝。"""
from __future__ import annotations

from datetime import date

from .config import settings
from .errors import TokenQuotaError
from .kvstore import get_kv


def _today() -> str:
    return date.today().isoformat()


def _key(user_id: int) -> str:
    return f"quota:tokens:{user_id}:{_today()}"


async def get_used(user_id: int) -> int:
    raw = await get_kv().get(_key(user_id))
    return int(raw) if raw else 0


async def add_tokens(user_id: int, count: int) -> int:
    if count <= 0:
        return await get_used(user_id)
    used = await get_kv().incrby(_key(user_id), count, ex=86400 * 2)
    await _maybe_warn(user_id, used)
    return used


async def get_warn_ratio(user_id: int) -> float:
    """提醒阈值：默认取全局配置，用户可在个人偏好里覆盖（键 token_warn_ratio）。"""
    try:
        from ..db.models import UserPreference
        from ..db.session import SessionLocal
        from sqlalchemy import select
        async with SessionLocal() as db:
            row = await db.scalar(select(UserPreference).where(
                UserPreference.user_id == user_id,
                UserPreference.pref_key == "token_warn_ratio"))
        if row and row.pref_value:
            val = float(row.pref_value)
            if 0 < val <= 1:
                return val
    except Exception:
        pass
    return settings.token_warn_ratio


async def _maybe_warn(user_id: int, used: int) -> None:
    """用量越过阈值时写一条站内消息（每天最多一次，避免刷屏）。"""
    quota = settings.token_daily_quota
    if not quota:
        return
    ratio = await get_warn_ratio(user_id)
    if used / quota < ratio:
        return
    flag = f"quota:warned:{user_id}:{_today()}"
    if not await get_kv().setnx(flag, "1", ex=86400 * 2):
        return                      # 今天已提醒过
    try:
        from ..db.session import SessionLocal
        from .notify import notify
        pct = round(used / quota * 100)
        async with SessionLocal() as db:
            await notify(db, user_id=user_id, kind="token",
                         title=f"Token 用量已达 {pct}%",
                         content=f"今日已用 {used} / {quota} tokens，接近每日配额上限，"
                                 f"建议精简提问或调低 topk，也可在消息中心调整提醒阈值。",
                         link="/messages")
            await db.commit()
    except Exception:
        pass


async def check_quota(user_id: int) -> None:
    used = await get_used(user_id)
    if used >= settings.token_daily_quota:
        raise TokenQuotaError()


async def usage_snapshot(user_id: int) -> dict:
    used = await get_used(user_id)
    quota = settings.token_daily_quota
    return {
        "used_tokens": used,
        "quota": quota,
        "remaining": max(0, quota - used),
        "warn_ratio": await get_warn_ratio(user_id),
        "warn_tokens": int(quota * await get_warn_ratio(user_id)),
        "date": _today(),
    }
