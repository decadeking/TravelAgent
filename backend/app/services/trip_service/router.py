"""trip-service：行程三级结构（行程 → 天 → 行程项）CRUD。

- 更新采用「先删后插」的全量替换，简单可靠；整体在一个事务内。
- 并发修改由 trips.version 乐观锁兜底，版本不匹配提示刷新。
- 列表按 (user_id, updated_at) 索引查询。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...common.errors import ConflictError, NotFoundError
from ...common.logging import get_logger
from ...common.notify import notify
from ...db.models import ItineraryItem, Trip, TripDay
from ...db.session import get_session
from ...gateway.deps import get_current_user
from ...schemas.common import ok
from ...schemas.trip import DayIn, TripCreateIn, TripUpdateIn
from ...db.models import User

router = APIRouter(prefix="/api/trips", tags=["trip-service"])
logger = get_logger("trips")


def _serialize(trip: Trip) -> dict:
    day_list = []
    total = 0.0
    for d in sorted(trip.day_list, key=lambda x: x.day_no):
        items = []
        for it in sorted(d.items, key=lambda x: x.seq):
            total += it.cost
            items.append({
                "id": it.id, "seq": it.seq, "time_slot": it.time_slot,
                "poi_name": it.poi_name, "category": it.category,
                "cost": it.cost, "duration_min": it.duration_min, "note": it.note,
            })
        day_list.append({
            "id": d.id, "day_no": d.day_no, "city": d.city,
            "weather_snapshot": d.weather_snapshot, "items": items,
        })
    return {
        "id": trip.id, "user_id": trip.user_id, "title": trip.title,
        "destination": trip.destination, "days": trip.days, "budget": trip.budget,
        "remark": trip.remark or "",
        "start_date": trip.start_date or "",
        "status": trip.status, "version": trip.version,
        "created_at": trip.created_at, "updated_at": trip.updated_at,
        "day_list": day_list, "total_cost": round(total, 2),
    }


def _apply_days(trip: Trip, day_list: list[DayIn]) -> None:
    """先删后插：全量替换行程的天与行程项。"""
    trip.day_list.clear()
    for d in day_list:
        day = TripDay(day_no=d.day_no, city=d.city, weather_snapshot=d.weather_snapshot)
        for it in d.items:
            day.items.append(ItineraryItem(
                seq=it.seq, time_slot=it.time_slot, poi_name=it.poi_name,
                category=it.category, cost=it.cost, duration_min=it.duration_min,
                note=it.note,
            ))
        trip.day_list.append(day)


async def _get_owned(trip_id: int, user_id: int, db: AsyncSession) -> Trip:
    trip = await db.scalar(
        select(Trip)
        .where(Trip.id == trip_id)
        .options(selectinload(Trip.day_list).selectinload(TripDay.items))
    )
    if trip is None or trip.user_id != user_id:
        raise NotFoundError("行程不存在")
    return trip


@router.get("")
async def list_trips(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    base = select(Trip).where(Trip.user_id == user.id)
    if status:
        base = base.where(Trip.status == status)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (await db.scalars(
        base.order_by(Trip.updated_at.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    items = [{
        "id": t.id, "title": t.title, "destination": t.destination, "days": t.days,
        "budget": t.budget, "remark": t.remark or "", "start_date": t.start_date or "",
        "status": t.status, "updated_at": t.updated_at,
    } for t in rows]
    return ok({"items": items, "page": page, "page_size": page_size, "total": total})


@router.post("")
async def create_trip(payload: TripCreateIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_session)):
    trip = Trip(
        user_id=user.id, title=payload.title, destination=payload.destination,
        days=payload.days, budget=payload.budget, status=payload.status, version=1,
        remark=payload.remark, start_date=payload.start_date or "",
    )
    _apply_days(trip, payload.day_list)
    db.add(trip)
    await db.flush()
    # 行程创建成功 → 写一条站内消息（右上角红点）
    await notify(db, user_id=user.id, kind="system", title="行程已保存",
                 content=f"{payload.title}（{payload.destination} · {payload.days} 天）",
                 link=f"/trips/{trip.id}")
    await db.commit()
    trip = await _get_owned(trip.id, user.id, db)
    # 「写死」开启提醒：确认出发日期后自动创建出发前/当天提醒（含桌面通知）
    await _enable_trip_reminders(user.id, trip)
    return ok(_serialize(trip))


async def _enable_trip_reminders(user_id: int, trip: Trip) -> list[dict]:
    """按行程出发日期创建提醒；失败只记日志，绝不影响行程保存。

    先取消该行程此前尚未触发的提醒，避免编辑日期后重复提醒。
    """
    if not (trip.start_date or "").strip():
        return []
    try:
        from sqlalchemy import update as sql_update

        from ...db.models import Reminder
        from ...db.session import SessionLocal

        async with SessionLocal() as db:
            await db.execute(
                sql_update(Reminder)
                .where(Reminder.trip_id == trip.id, Reminder.status == "pending")
                .values(status="cancelled"))
            await db.commit()

        from ..agent_service.reminders import create_trip_reminders
        return await create_trip_reminders(
            user_id=user_id, trip_id=trip.id, title=trip.title,
            destination=trip.destination, start_date=trip.start_date)
    except Exception as exc:
        logger.warning("行程提醒创建失败（不影响保存）: %s", exc)
        return []


@router.get("/{trip_id}")
async def get_trip(trip_id: int, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_session)):
    trip = await _get_owned(trip_id, user.id, db)
    return ok(_serialize(trip))


@router.put("/{trip_id}")
async def update_trip(trip_id: int, payload: TripUpdateIn,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_session)):
    trip = await _get_owned(trip_id, user.id, db)
    if payload.version is not None and payload.version != trip.version:
        raise ConflictError("行程已被其他窗口修改，请刷新后重试")
    prev_start = trip.start_date or ""
    current_version = trip.version
    # 乐观锁：先以 WHERE version=旧值 占位递增，并发窗口内版本被抢改则 0 行命中
    from sqlalchemy import update as sql_update
    result = await db.execute(
        sql_update(Trip)
        .where(Trip.id == trip_id, Trip.version == current_version)
        .values(version=current_version + 1))
    if result.rowcount == 0:
        await db.rollback()
        raise ConflictError("行程已被其他窗口修改，请刷新后重试")
    for field in ("title", "destination", "days", "budget", "remark", "start_date", "status"):
        val = getattr(payload, field)
        if val is not None:
            setattr(trip, field, val)
    if payload.day_list is not None:
        _apply_days(trip, payload.day_list)
    trip.version = current_version + 1
    await db.commit()
    trip = await _get_owned(trip_id, user.id, db)
    # 编辑时新填/变更了出发日期 → 重新开启提醒（同一天只补一次，不加重复）
    if (trip.start_date or "").strip() and trip.start_date != prev_start:
        await _enable_trip_reminders(user.id, trip)
    return ok(_serialize(trip))


@router.delete("/{trip_id}")
async def delete_trip(trip_id: int, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_session)):
    trip = await _get_owned(trip_id, user.id, db)
    await db.delete(trip)
    await db.commit()
    return ok({"deleted": trip_id})
