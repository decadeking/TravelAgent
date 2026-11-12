"""网关注入上下文与鉴权依赖。

对应设计：网关是唯一入口，负责 JWT 鉴权、注入全局 trace_id / request_id、
把 user_id 注入请求上下文；下游服务信任上下文，不重复校验。
本模块在「逻辑微服务」形态下以 FastAPI 依赖 + 中间件实现同样职责。
"""
from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ..common import context
from ..common.errors import ForbiddenError, UnauthorizedError
from ..common.security import decode_token
from ..db.models import User
from ..db.session import get_session


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_session),
) -> User:
    """解析 Bearer Token → 注入上下文 → 返回当前用户。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("缺少登录凭证")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    user_id = int(payload.get("sub", 0))
    username = payload.get("username", "")
    if not user_id:
        raise UnauthorizedError("无效的登录凭证")
    user = await db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("用户不存在或已注销")
    # 注入协程上下文：下游服务信任该 user_id
    context.set_user(user.id, user.username)
    return user


async def get_optional_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_session),
) -> User | None:
    if not authorization:
        return None
    try:
        return await get_current_user(authorization, db)
    except UnauthorizedError:
        return None


def ensure_owner(owner_id: int, user: User) -> None:
    """数据接口按 user_id 过滤，防越权。"""
    if owner_id != user.id:
        raise ForbiddenError("无权访问该资源")


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """管理员专属依赖。"""
    if (user.role or "user") != "admin":
        raise ForbiddenError("需要管理员权限")
    return user


async def require_active_user(user: User = Depends(get_current_user)) -> User:
    """社区互动依赖：被管理员拉黑（黑名单）的用户禁止发帖/点赞/评论/收藏等写操作。"""
    if getattr(user, "banned", 0):
        reason = (getattr(user, "ban_reason", "") or "").strip()
        raise ForbiddenError(
            f"你已被管理员加入黑名单，暂时无法发布动态或互动。{('原因：' + reason) if reason else ''}")
    return user

