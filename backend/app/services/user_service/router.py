"""user-service：注册登录、偏好管理、Token 配额。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from ...common.notify import notify
from ...common.quota import usage_snapshot
from ...common.security import create_access_token, hash_password, verify_password
from ...db.models import Follow, User, UserPreference
from ...db.session import get_session
from ...gateway.deps import get_current_user, require_active_user
from ...schemas.auth import LoginIn, ModelConfigIn, PreferenceIn, ProfileUpdateIn, RegisterIn
from ...schemas.common import ok

router = APIRouter(tags=["user-service"])


def _user_dict(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "nickname": u.nickname or u.username,
        "avatar": u.avatar or "", "cover": u.cover or "",
        "role": u.role or "user", "bio": u.bio or "",
        "banned": bool(getattr(u, "banned", 0)),
        "created_at": u.created_at,
    }


@router.post("/api/auth/register")
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_session)):
    exists = await db.scalar(select(User).where(User.username == payload.username))
    if exists:
        raise ConflictError("用户名已被占用")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname or payload.username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token, expires_in = create_access_token(user.id, user.username)
    return ok({"access_token": token, "token_type": "bearer",
               "expires_in": expires_in, "user": _user_dict(user)})


@router.post("/api/auth/login")
async def login(payload: LoginIn, db: AsyncSession = Depends(get_session)):
    user = await db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("用户名或密码错误")
    token, expires_in = create_access_token(user.id, user.username)
    return ok({"access_token": token, "token_type": "bearer",
               "expires_in": expires_in, "user": _user_dict(user)})


@router.get("/api/users/me")
async def me(user: User = Depends(get_current_user)):
    return ok(_user_dict(user))


@router.put("/api/users/me")
async def update_me(payload: ProfileUpdateIn,
                    user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_session)):
    """更新个人资料（昵称 / 头像 / 简介）。

    头像统一落到后端资源文件夹：data: URL、外链会先落盘再写库，
    保证数据库里存的是「后端调用路径」而不是路径文字或 data URL。
    """
    if payload.nickname is not None:
        user.nickname = payload.nickname
    if payload.avatar is not None:
        from ..media_service.router import materialize_or_keep
        url, err = await materialize_or_keep(db, payload.avatar, owner_id=user.id, kind="avatar")
        if err:
            raise ValidationError(f"头像保存失败：{err}")
        user.avatar = url
    if payload.bio is not None:
        user.bio = payload.bio
    if payload.cover is not None:
        from ..media_service.router import materialize_or_keep
        url, err = await materialize_or_keep(db, payload.cover, owner_id=user.id, kind="image")
        if err:
            raise ValidationError(f"背景图保存失败：{err}")
        user.cover = url
    await db.commit()
    await db.refresh(user)
    return ok(_user_dict(user))


@router.get("/api/users/preferences")
async def get_preferences(user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_session)):
    rows = (await db.scalars(
        select(UserPreference).where(UserPreference.user_id == user.id))).all()
    return ok({r.pref_key: r.pref_value for r in rows})


@router.put("/api/users/preferences")
async def put_preferences(payload: PreferenceIn,
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_session)):
    """全量覆盖用户偏好（长期记忆）。"""
    await db.execute(delete(UserPreference).where(UserPreference.user_id == user.id))
    for k, v in payload.preferences.items():
        db.add(UserPreference(user_id=user.id, pref_key=k[:64], pref_value=str(v)[:255]))
    await db.commit()
    return ok(payload.preferences)


@router.get("/api/users/usage")
async def usage(user: User = Depends(get_current_user)):
    return ok(await usage_snapshot(user.id))


@router.get("/api/users/model-config")
async def get_model_config(user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_session)):
    """返回可选模型（固定配置）与该用户是否已配置密钥；不回传密钥本身。"""
    from ...common.runtime_config import runtime_config
    from ...common.user_model import get_user_model_config

    cfg = await runtime_config.get_llm()
    mine = await get_user_model_config(db, user.id)
    return ok({
        "models": cfg.get("models", []),
        "default_model": cfg.get("default_model", "deepseek-v4-flash"),
        "selected_model": mine.get("model") or cfg.get("default_model", "deepseek-v4-flash"),
        "has_api_key": bool(mine.get("api_key") or cfg.get("api_key")),
        "has_own_api_key": bool(mine.get("api_key")),
    })


@router.put("/api/users/model-config")
async def put_model_config(payload: ModelConfigIn,
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_session)):
    from ...common.user_model import save_user_model_config

    mine = await save_user_model_config(db, user.id, api_key=payload.api_key,
                                        model=payload.model,
                                        clear_api_key=payload.clear_api_key)
    return ok({"has_api_key": mine["has_api_key"], "model": mine["model"]})


@router.post("/api/users/model-config/test")
async def test_model_config(payload: ModelConfigIn | None = None,
                            user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_session)):
    """连通性自检：用当前（或刚填入的）密钥真实调用一次，返回可用模型或可读错误。"""
    from ...common.runtime_config import runtime_config
    from ...common.user_model import get_user_model_config
    from ..agent_service.llm.adapter import llm

    mine = await get_user_model_config(db, user.id)
    cfg = await runtime_config.get_llm()
    key = (payload.api_key if payload and payload.api_key else "") or mine.get("api_key") \
        or cfg.get("api_key") or ""
    model = (payload.model if payload and payload.model else "") or mine.get("model") \
        or cfg.get("default_model")
    if not key.strip():
        return ok({"ok": False, "message": "尚未配置 API Key，规划将使用离线模拟输出。"})
    result = await llm.ping(model=model, api_key=key)
    return ok(result)


# ───────────────────── 关注 / 好友（互关才是好友） ─────────────────────

def _user_card(u: User) -> dict:
    return {"id": u.id, "username": u.username,
            "nickname": u.nickname or u.username, "avatar": u.avatar or "",
            "bio": u.bio or ""}


async def _relation(db: AsyncSession, me: int, other: int) -> tuple[bool, bool]:
    i_follow = await db.scalar(select(Follow).where(
        Follow.follower_id == me, Follow.following_id == other))
    follows_me = await db.scalar(select(Follow).where(
        Follow.follower_id == other, Follow.following_id == me))
    return bool(i_follow), bool(follows_me)


@router.get("/api/users/friends")
async def list_friends(user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_session)):
    """好友 = 互相关注的人。单向关注只是「关注」，不构成好友。"""
    mine = (await db.scalars(select(Follow).where(Follow.follower_id == user.id))).all()
    theirs = (await db.scalars(select(Follow).where(Follow.following_id == user.id))).all()
    i_follow_ids = {f.following_id for f in mine}
    follows_me_ids = {f.follower_id for f in theirs}
    mutual_ids = i_follow_ids & follows_me_ids
    if not mutual_ids:
        return ok([])
    users = (await db.scalars(select(User).where(User.id.in_(mutual_ids)))).all()
    return ok([{**_user_card(u), "following": True, "mutual": True} for u in users])


@router.get("/api/users/following")
async def list_following(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_session)):
    """我关注的人（含是否已互关成为好友）。"""
    rows = (await db.scalars(select(Follow).where(
        Follow.follower_id == user.id).order_by(Follow.created_at.desc()))).all()
    ids = [f.following_id for f in rows]
    if not ids:
        return ok([])
    # 关注我的人 → 与「我关注的」取交集即为好友（互关）
    followers = (await db.scalars(
        select(Follow.follower_id).where(Follow.following_id == user.id))).all()
    follows_me = set(followers)
    users = (await db.scalars(select(User).where(User.id.in_(ids)))).all()
    order = {uid: i for i, uid in enumerate(ids)}
    users.sort(key=lambda u: order.get(u.id, 999))
    return ok([{**_user_card(u), "following": True,
                "mutual": u.id in follows_me} for u in users])


@router.get("/api/users/followers")
async def list_followers(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_session)):
    rows = (await db.scalars(select(Follow).where(
        Follow.following_id == user.id).order_by(Follow.created_at.desc()))).all()
    ids = [f.follower_id for f in rows]
    if not ids:
        return ok([])
    following = (await db.scalars(
        select(Follow.following_id).where(Follow.follower_id == user.id))).all()
    i_follow = set(following)
    users = (await db.scalars(select(User).where(User.id.in_(ids)))).all()
    order = {uid: i for i, uid in enumerate(ids)}
    users.sort(key=lambda u: order.get(u.id, 999))
    return ok([{**_user_card(u), "following": u.id in i_follow,
                "mutual": u.id in i_follow} for u in users])


@router.get("/api/users/discover")
async def discover_users(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_session)):
    """可能认识的人：还没关注的用户（排除自己），供好友页推荐。"""
    followed = (await db.scalars(select(Follow).where(Follow.follower_id == user.id))).all()
    exclude = {f.following_id for f in followed} | {user.id}
    users = (await db.scalars(
        select(User).order_by(User.created_at.desc()).limit(30))).all()
    return ok([_user_card(u) for u in users if u.id not in exclude][:12])


@router.get("/api/users/{user_id}")
async def get_user_public(user_id: int, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_session)):
    target = await db.get(User, user_id)
    if target is None:
        raise NotFoundError("用户不存在")
    i_follow, follows_me = await _relation(db, user.id, user_id)
    followers = await db.scalar(select(func.count()).select_from(Follow)
                                .where(Follow.following_id == user_id)) or 0
    following = await db.scalar(select(func.count()).select_from(Follow)
                                .where(Follow.follower_id == user_id)) or 0
    return ok({**_user_card(target), "is_me": target.id == user.id,
               "following": i_follow, "followed_by": follows_me,
               "is_friend": i_follow and follows_me,
               "followers": int(followers), "following_count": int(following)})


@router.post("/api/users/{user_id}/follow")
async def toggle_follow(user_id: int, user: User = Depends(require_active_user),
                        db: AsyncSession = Depends(get_session)):
    """关注/取关。

    - 单向关注只是「关注」，提示关注成功，不构成好友；
    - 对方也关注了你（回关）时双方才成为好友，并各收到一条「成为好友」通知。
    """
    if user_id == user.id:
        raise ValidationError("不能关注自己")
    target = await db.get(User, user_id)
    if target is None:
        raise NotFoundError("用户不存在")
    row = await db.scalar(select(Follow).where(
        Follow.follower_id == user.id, Follow.following_id == user_id))
    if row:
        await db.delete(row)
        following = False
    else:
        db.add(Follow(follower_id=user.id, following_id=user_id))
        following = True
        who = user.nickname or user.username
        target_name = target.nickname or target.username
        # 对方是否已经关注我 → 本次关注后是否互为好友
        back = await db.scalar(select(Follow).where(
            Follow.follower_id == user_id, Follow.following_id == user.id))
        # 通知被关注的人（只说「关注了你」，不提好友关系）
        await notify(db, user_id=user_id, kind="follow",
                     title=f"{who} 关注了你",
                     content="TA 的动态会出现在你的「动态」里，也可以回关。",
                     actor_id=user.id, link=f"/u/{user.id}")
        # 关注成功的回执（发给自己）
        await notify(db, user_id=user.id, kind="follow",
                     title=f"关注成功：{target_name}",
                     content=f"已成功关注「{target_name}」，TA 的动态会出现在你的「动态」里。",
                     link=f"/u/{user_id}")
        if back:
            # 互相关注达成 → 双方成为好友，各发一条通知
            await notify(db, user_id=user.id, kind="follow",
                         title=f"你与 {target_name} 已成为好友",
                         content="你们已互相关注，现在可以查看对方的「好友可见」动态了。",
                         actor_id=user_id, link=f"/u/{user_id}")
            await notify(db, user_id=user_id, kind="follow",
                         title=f"你与 {who} 已成为好友",
                         content="你们已互相关注，现在可以查看对方的「好友可见」动态了。",
                         actor_id=user.id, link=f"/u/{user.id}")
    await db.commit()
    return ok({"following": following})
