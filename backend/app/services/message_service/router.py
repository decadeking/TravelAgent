"""message-service：站内消息中心。

聚合展示：他人点赞 / 评论 / 回复 / 关注、收藏成功、Token 用量提醒、行程提醒，
并提供未读计数与已读标记，供侧边栏徽标与右上角铃铛轮询。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.notify import KIND_LABEL
from ...db.models import Notification, User
from ...db.session import get_session
from ...gateway.deps import get_current_user
from ...schemas.common import ok

router = APIRouter(prefix="/api/messages", tags=["message-service"])


async def _serialize(db: AsyncSession, rows: list[Notification]) -> list[dict]:
    actor_ids = {r.actor_id for r in rows if r.actor_id}
    actors: dict[int, User] = {}
    if actor_ids:
        got = (await db.scalars(select(User).where(User.id.in_(actor_ids)))).all()
        actors = {u.id: u for u in got}
    out = []
    for r in rows:
        a = actors.get(r.actor_id) if r.actor_id else None
        out.append({
            "id": r.id,
            "kind": r.kind,
            "kind_label": KIND_LABEL.get(r.kind, "系统"),
            "title": r.title,
            "content": r.content,
            "post_id": r.post_id,
            "link": r.link,
            "read": bool(r.read),
            "created_at": r.created_at.isoformat(sep=" ", timespec="minutes") if r.created_at else None,
            "actor": {
                "id": a.id, "nickname": (a.nickname or a.username) if a else "",
                "avatar": a.avatar if a else "",
            } if a else None,
        })
    return out


async def _counts(db: AsyncSession, user_id: int) -> tuple[int, dict[str, int]]:
    unread = await db.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read == 0)) or 0
    rows = (await db.execute(
        select(Notification.kind, func.count())
        .where(Notification.user_id == user_id, Notification.read == 0)
        .group_by(Notification.kind))).all()
    return int(unread), {k: int(n) for k, n in rows}


@router.get("")
async def list_messages(kind: str | None = None,
                        unread_only: bool = False,
                        page: int = Query(1, ge=1),
                        page_size: int = Query(30, ge=1, le=100),
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_session)):
    """消息列表（可按分类过滤）+ 未读计数（按分类）。"""
    base = select(Notification).where(Notification.user_id == user.id)
    if kind and kind != "all":
        base = base.where(Notification.kind == kind)
    if unread_only:
        base = base.where(Notification.read == 0)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (await db.scalars(
        base.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    unread, counts = await _counts(db, user.id)
    return ok({"items": await _serialize(db, rows), "total": total,
               "page": page, "page_size": page_size, "unread": unread,
               "counts": counts, "kinds": KIND_LABEL})


@router.get("/summary")
async def messages_summary(user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_session)):
    """轻量接口：仅供徽标 / 铃铛高频轮询。"""
    unread, counts = await _counts(db, user.id)
    latest = (await db.scalars(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc()).limit(5))).all()
    return ok({"unread": unread, "counts": counts,
               "latest": await _serialize(db, latest)})


@router.post("/read")
async def mark_read(kind: str | None = None,
                    user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_session)):
    """标记已读：带 kind 只清该分类，否则全部。"""
    stmt = update(Notification).where(Notification.user_id == user.id,
                                      Notification.read == 0)
    if kind and kind != "all":
        stmt = stmt.where(Notification.kind == kind)
    await db.execute(stmt.values(read=1))
    await db.commit()
    unread, counts = await _counts(db, user.id)
    return ok({"unread": unread, "counts": counts})


@router.post("/{message_id}/read")
async def mark_one_read(message_id: int, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_session)):
    await db.execute(update(Notification)
                     .where(Notification.id == message_id, Notification.user_id == user.id)
                     .values(read=1))
    await db.commit()
    unread, _ = await _counts(db, user.id)
    return ok({"id": message_id, "unread": unread})


@router.delete("/{message_id}")
async def delete_message(message_id: int, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_session)):
    await db.execute(sql_delete(Notification)
                     .where(Notification.id == message_id, Notification.user_id == user.id))
    await db.commit()
    unread, _ = await _counts(db, user.id)
    return ok({"deleted": message_id, "unread": unread})


@router.delete("")
async def clear_messages(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_session)):
    """清空消息（用户手动删除，符合「除非我点击删除否则不丢失」的预期）。"""
    await db.execute(sql_delete(Notification).where(Notification.user_id == user.id))
    await db.commit()
    return ok({"cleared": True, "unread": 0})
