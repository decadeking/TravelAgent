"""行程提醒：时间解析 + 落库 + 后台触发。

- `parse_remind_at`：把「明天早上8点」「3天后」「2026-11-01 09:00」等
  自然语言解析成绝对时间；
- `create_reminder`：智能体调用 set_reminder 工具时写入 reminders 表；
- `reminder_loop`：后台调度，每 30 秒扫一次到期提醒 → 写 notifications 表。
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

from ...common import context
from ...common.logging import get_logger
from ...db.models import Notification, Reminder
from ...db.session import SessionLocal

logger = get_logger("reminders")

_PERIOD_HOUR = {"早上": 8, "上午": 9, "中午": 12, "下午": 14, "傍晚": 18, "晚上": 20}
_DEFAULT_HOUR = 9


def parse_remind_at(text: str | None, *, now: datetime | None = None) -> datetime:
    """把自然语言时间解析为绝对时间；解析不出则默认「明天 09:00」。"""
    now = now or datetime.now()
    raw = (text or "").strip()
    if not raw:
        return (now + timedelta(days=1)).replace(hour=_DEFAULT_HOUR, minute=0, second=0, microsecond=0)

    # 1) 显式日期时间：2026-11-01 / 2026-11-01 09:00 / 11-01 09:00
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2})[:：](\d{1,2}))?", raw)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4)) if m.group(4) else _DEFAULT_HOUR
        mm = int(m.group(5)) if m.group(5) else 0
        try:
            return datetime(y, mo, d, hh, mm)
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2})[:：](\d{1,2}))?", raw)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        hh = int(m.group(3)) if m.group(3) else _DEFAULT_HOUR
        mm = int(m.group(4)) if m.group(4) else 0
        try:
            cand = datetime(now.year, mo, d, hh, mm)
            if cand < now:
                cand = cand.replace(year=now.year + 1)
            return cand
        except ValueError:
            pass

    hour = _DEFAULT_HOUR
    for kw, hh in _PERIOD_HOUR.items():
        if kw in raw:
            hour = hh
            break
    hm = re.search(r"(\d{1,2})\s*[:：点]\s*(\d{1,2})?", raw)
    if hm:
        hour = int(hm.group(1))
        minute = int(hm.group(2)) if hm.group(2) else 0
    else:
        minute = 0

    base = now
    if "后天" in raw:
        base = now + timedelta(days=2)
    elif "明天" in raw or "明日" in raw:
        base = now + timedelta(days=1)
    else:
        dm = re.search(r"(\d+)\s*天(?:后|以后)", raw)
        if dm:
            base = now + timedelta(days=int(dm.group(1)))
        else:
            hmm = re.search(r"(\d+)\s*(?:个)?小时(?:后|以后)", raw)
            if hmm:
                base = now + timedelta(hours=int(hmm.group(1)))
            else:
                wm = re.search(r"(\d+)\s*(?:个)?(?:周|星期)(?:后|以后)", raw)
                if wm:
                    base = now + timedelta(weeks=int(wm.group(1)))
                else:
                    base = now
    cand = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if cand <= now:
        cand = cand + timedelta(days=1)
    return cand


def format_remind(cn: datetime) -> str:
    return cn.strftime("%Y-%m-%d %H:%M")


async def create_reminder(*, user_id: int | None, title: str, when: str,
                          detail: str = "", trip_id: int | None = None,
                          source: str = "agent", desktop: bool = False) -> dict:
    """写入一条提醒，返回可读结果（供工具回喂给模型）。"""
    uid = user_id or context.get_user_id()
    if not uid:
        return {"error": "无法确定用户身份，未能创建提醒"}
    remind_at = parse_remind_at(when)
    async with SessionLocal() as db:
        row = Reminder(user_id=uid, trip_id=trip_id,
                       title=(title or "行程提醒")[:200],
                       detail=(detail or "")[:2000],
                       remind_at=remind_at, source=source,
                       desktop=1 if desktop else 0)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    logger.info("已创建行程提醒", extra={"tool": f"id={row.id} at={format_remind(remind_at)}"})
    return {"reminder_id": row.id, "title": row.title,
            "remind_at": format_remind(remind_at),
            "hint": f"已设置提醒：{format_remind(remind_at)}「{row.title}」"}


async def create_trip_reminders(*, user_id: int, trip_id: int, title: str,
                                destination: str, start_date: str) -> list[dict]:
    """行程创建后「写死」开启提醒（个人行程 / 规划保存共用）。

    两条提醒：
    - 出发前一日 20:00：站内提醒，提示打包与行程核对；
    - 出发当天 08:00：站内提醒 + 桌面通知（desktop-notification）。
    日期非法或已过期则跳过，绝不因提醒失败影响行程保存。
    """
    from datetime import date as _date  # noqa: F401  (按日历日计算，语义保留)
    try:
        d = datetime.strptime((start_date or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return []
    now = datetime.now()
    out: list[dict] = []
    # ① 出发前一天 20:00
    eve = datetime.combine(d - timedelta(days=1), datetime.min.time()).replace(hour=20)
    if eve > now:
        out.append(await create_reminder(
            user_id=user_id, trip_id=trip_id, source="trip", desktop=False,
            title=f"出行前提醒：明天出发去{destination}",
            when=eve.strftime("%Y-%m-%d %H:%M"),
            detail=f"「{title}」将于 {d.isoformat()} 出发，记得打包行李、核对交通与住宿。"))
    # ② 出发当天 08:00（桌面通知）
    day = datetime.combine(d, datetime.min.time()).replace(hour=8)
    if day > now:
        out.append(await create_reminder(
            user_id=user_id, trip_id=trip_id, source="trip", desktop=True,
            title=f"旅行当天提醒：今天出发去{destination}",
            when=day.strftime("%Y-%m-%d %H:%M"),
            detail=f"「{title}」今天出发，带好证件，注意天气与交通，祝旅途愉快！"))
    return out


async def _desktop_notify(user_id: int, title: str, content: str) -> None:
    """触发桌面通知：优先走 MCP desktop-notification 工具，失败回落本地气泡。

    站内通知已由 _fire_due 写入，这里传 write_notification=False 避免重复。
    """
    payload = {"user_id": user_id, "title": title, "content": content,
               "write_notification": False}
    try:
        from ..mcp_service.manager import mcp_manager
        if mcp_manager.enabled:
            await mcp_manager.call_tool("notify_desktop", payload)
            return
    except Exception as exc:
        logger.warning("MCP 桌面通知失败，回落本地气泡: %s", exc)
    try:
        from ..mcp_service.desktop import show_toast
        show_toast(title, content)
    except Exception:
        pass


async def _fire_due() -> int:
    """把到期提醒转成通知（标记 desktop 的再弹一次桌面气泡）。"""
    now = datetime.now()
    fired = 0
    async with SessionLocal() as db:
        from sqlalchemy import select
        rows = (await db.scalars(
            select(Reminder).where(Reminder.status == "pending",
                                   Reminder.remind_at <= now))).all()
        due = [(r.user_id, r.title or "行程提醒", (r.detail or "")[:500], bool(r.desktop))
               for r in rows]
        for r in rows:
            db.add(Notification(user_id=r.user_id, kind="reminder",
                                title=r.title or "行程提醒",
                                content=(r.detail or "")[:500]))
            r.status = "fired"
            fired += 1
        if fired:
            await db.commit()
    # 桌面通知放在事务外，避免外部进程/网络调用拖长数据库事务
    for uid, title, content, desktop in due:
        if desktop:
            await _desktop_notify(uid, title, content)
    return fired


async def reminder_loop(interval: int = 30) -> None:
    """后台常驻：定期触达到期提醒（失败不致命，下轮继续）。"""
    while True:
        try:
            n = await _fire_due()
            if n:
                logger.info("触发提醒", extra={"tool": f"count={n}"})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("提醒调度异常: %s", exc)
        await asyncio.sleep(interval)
