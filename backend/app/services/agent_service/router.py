"""agent-service 路由：SSE 对话 + 会话状态恢复。"""
from __future__ import annotations

import random
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.errors import ForbiddenError
from ...db.models import AgentSession, User
from ...db.session import get_session
from ...gateway.deps import get_current_user
from ...schemas.agent import ChatIn
from ...schemas.common import ok
from .guard.prompt_guard import prompt_guard
from .memory.short_term import session_memory
from .service import chat_event_stream

router = APIRouter(prefix="/api/agent", tags=["agent-service"])


async def _assert_session_owner(db: AsyncSession, session_id: str, user_id: int) -> None:
    """校验会话归属：DB 行或 Redis 上下文里记录的 user_id 必须与当前用户一致。

    修复「多用户共用一个上下文」：此前 chat 接口对传入的 session_id 不做归属校验，
    且秒级时间戳生成可能让不同用户在同一秒撞号，导致两人对话互相串扰。
    """
    row = await db.scalar(select(AgentSession).where(AgentSession.session_id == session_id))
    if row is not None:
        owner = row.user_id
    else:
        owner = (await session_memory.load(session_id)).get("user_id")
    if owner is not None and owner != user_id:
        raise ForbiddenError("会话不存在或无权访问")


@router.post("/chat")
async def chat(payload: ChatIn, user: User = Depends(get_current_user),
               db: AsyncSession = Depends(get_session)):
    """发起规划对话，返回 SSE 流（全系统唯一的 SSE 接口）。"""
    message = prompt_guard.check_input(payload.message)
    if payload.session_id:
        # 续聊已有会话：先验归属，防止拿别人的 session_id 读写其上下文
        await _assert_session_owner(db, payload.session_id, user.id)
    # 会话名（即 session_id）采用「s + 月日时时分秒 + 3 位随机数字」的可读格式：
    # 时间前缀便于历史列表辨认（保持纯数字、不混字母），随机后缀保证跨用户全局唯一，
    # 杜绝两个用户同一秒新建会话撞号后共用一份上下文
    session_id = payload.session_id or f"s{datetime.now():%m%d%H%M%S}{random.randint(100, 999)}"
    request_id = payload.request_id or uuid.uuid4().hex
    generator = chat_event_stream(
        user_id=user.id, username=user.username,
        session_id=session_id, message=message, request_id=request_id,
        model=payload.model, tools=payload.tools,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/models")
async def list_models(user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_session)):
    """可选模型列表（供规划页模型选择器）。"""
    from ...common.runtime_config import runtime_config
    from ...common.user_model import get_user_model_config

    cfg = await runtime_config.get_llm()
    mine = await get_user_model_config(db, user.id)
    return ok({
        "models": cfg.get("models", []),
        "default_model": mine.get("model") or cfg.get("default_model", "deepseek-v4-flash"),
        "provider": cfg.get("provider", "deepseek"),
        "has_api_key": bool(mine.get("api_key") or cfg.get("api_key")),
    })


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_session)):
    rows = (await db.scalars(
        select(AgentSession).where(AgentSession.user_id == user.id)
        .order_by(AgentSession.created_at.desc()).limit(30))).all()
    return ok([{
        "session_id": r.session_id, "summary": r.summary,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows])


@router.get("/sessions/{session_id}")
async def get_session_state(session_id: str, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_session)):
    """会话历史与状态恢复（checkpointer 落 Redis，读回无需重新调用大模型）。"""
    live = await session_memory.load(session_id)
    row = await db.scalar(select(AgentSession).where(AgentSession.session_id == session_id))
    # 归属校验：DB 行优先，行未落库时用上下文里的 user_id；对不上一律视为不存在
    owner = row.user_id if row else live.get("user_id")
    if owner != user.id:
        return ok(None)
    if not live and row is None:
        return ok(None)
    return ok({
        "session_id": session_id,
        "summary": live.get("summary") or (row.summary if row else ""),
        "messages": live.get("messages", []),
        "slots": live.get("slots", {}),
        "plan_draft": live.get("plan_draft"),
        "revision_count": live.get("revision_count", 0),
        "can_resume": bool(live.get("messages")),
    })


# ───────────────── 行程提醒 与 站内通知 ─────────────────

@router.get("/reminders")
async def list_reminders(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_session)):
    from ...db.models import Reminder
    rows = (await db.scalars(
        select(Reminder).where(Reminder.user_id == user.id)
        .order_by(Reminder.remind_at.asc()).limit(50))).all()
    return ok([{
        "id": r.id, "title": r.title, "detail": r.detail,
        "remind_at": r.remind_at.isoformat(sep=" ", timespec="minutes") if r.remind_at else None,
        "status": r.status, "source": r.source,
    } for r in rows])


@router.post("/reminders")
async def create_reminder_api(payload: dict,
                              user: User = Depends(get_current_user)):
    """手动创建提醒（智能体也会通过 set_reminder 工具创建）。"""
    from .reminders import create_reminder
    result = await create_reminder(
        user_id=user.id, title=str(payload.get("title") or "行程提醒"),
        when=str(payload.get("when") or ""), detail=str(payload.get("detail") or ""))
    if result.get("error"):
        return ok(result)
    result["source"] = "manual"
    return ok(result)


@router.delete("/reminders/{reminder_id}")
async def cancel_reminder(reminder_id: int, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_session)):
    from ...db.models import Reminder
    row = await db.scalar(select(Reminder).where(Reminder.id == reminder_id,
                                                 Reminder.user_id == user.id))
    if row:
        row.status = "cancelled"
        await db.commit()
    return ok({"cancelled": reminder_id})


@router.get("/notifications")
async def list_notifications(unread_only: bool = False,
                             user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_session)):
    from ...db.models import Notification
    from sqlalchemy import func
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read == 0)
    rows = (await db.scalars(stmt.order_by(Notification.created_at.desc()).limit(50))).all()
    unread = await db.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read == 0)) or 0
    return ok({"unread": unread, "items": [{
        "id": r.id, "title": r.title, "content": r.content, "kind": r.kind,
        "read": bool(r.read),
        "created_at": r.created_at.isoformat(sep=" ", timespec="minutes") if r.created_at else None,
    } for r in rows]})


@router.post("/notifications/read")
async def mark_notifications_read(user: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_session)):
    from ...db.models import Notification
    from sqlalchemy import update
    await db.execute(update(Notification).where(Notification.user_id == user.id,
                                                Notification.read == 0).values(read=1))
    await db.commit()
    return ok({"ok": True})
