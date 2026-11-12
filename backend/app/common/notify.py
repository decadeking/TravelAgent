"""站内消息写入（社交动作 / 提醒 / Token 配额共用）。

统一收敛「谁给谁发了什么消息」这一件事，避免各服务各写一套。
默认只 add 不 commit——由调用方在其事务里提交，保证与业务动作同源。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Notification

# 消息分类中文名（前端展示与聚合统计共用）
KIND_LABEL: dict[str, str] = {
    "like": "点赞",
    "comment": "评论",
    "reply": "回复",
    "follow": "关注",
    "collect": "收藏",
    "token": "用量提醒",
    "reminder": "行程提醒",
    "system": "系统",
}


async def notify(db: AsyncSession, *, user_id: int | None, kind: str, title: str,
                 content: str = "", actor_id: int | None = None,
                 post_id: int | None = None, link: str = "") -> Notification | None:
    """写入一条站内消息；自己触发的动作不会给自己发消息。"""
    if not user_id or kind not in KIND_LABEL:
        return None
    if actor_id and actor_id == user_id:
        return None
    row = Notification(user_id=user_id, kind=kind, title=title[:200],
                       content=(content or "")[:500], actor_id=actor_id,
                       post_id=post_id, link=(link or "")[:255])
    db.add(row)
    return row
