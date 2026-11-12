"""feed-service：旅行吧（社交动态）。

帖子发布 / 编辑 / 删除（作者本人）、动态流、详情、点赞、收藏、留言，
以及管理员审核（下架 / 通过 / 删除）。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.errors import ForbiddenError, NotFoundError, ValidationError
from ...common.notify import notify
from ...db.models import Comment, Post, PostCollect, PostLike, User
from ...db.session import get_session
from ...gateway.deps import get_current_user, require_active_user
from ...schemas.common import ok
from ...schemas.feed import CommentIn, PostIn

router = APIRouter(prefix="/api/posts", tags=["feed-service"])
admin_router = APIRouter(prefix="/api/admin/posts", tags=["feed-service"])


def _loads(raw: str) -> list:
    try:
        val = json.loads(raw or "[]")
        return val if isinstance(val, list) else []
    except Exception:
        return []


async def _liked_collected(db: AsyncSession, post_id: int, user_id: int | None) -> tuple[bool, bool]:
    if not user_id:
        return False, False
    liked = await db.scalar(select(PostLike).where(
        PostLike.post_id == post_id, PostLike.user_id == user_id, PostLike.active == 1))
    collected = await db.scalar(select(PostCollect).where(
        PostCollect.post_id == post_id, PostCollect.user_id == user_id))
    return bool(liked), bool(collected)


# ─────────────── 帖子可见范围 ───────────────
# public：全部可见；friends：仅「互关好友」与作者本人可见；private：仅作者本人可见。

async def _mutual_ids(db: AsyncSession, user_id: int) -> set[int]:
    """好友 = 互相关注（我关注了 TA，且 TA 也关注了我）。"""
    from ...db.models import Follow
    mine = set((await db.scalars(
        select(Follow.following_id).where(Follow.follower_id == user_id))).all())
    theirs = set((await db.scalars(
        select(Follow.follower_id).where(Follow.following_id == user_id))).all())
    return mine & theirs


def _visibility_clause(user: User | None, mutual_ids: set[int]):
    """按可见范围生成 SQL 过滤条件；管理员不做限制（审核需要看到全部）。"""
    if user is not None and user.role == "admin":
        return None
    if user is None:
        return Post.visibility == "public"
    friend_ids = [user.id, *mutual_ids]
    return or_(
        Post.visibility == "public",
        and_(Post.visibility == "friends", Post.user_id.in_(friend_ids)),
        and_(Post.visibility == "private", Post.user_id == user.id),
    )


async def _can_view(db: AsyncSession, post: Post, user: User | None,
                    mutual: set[int] | None = None) -> bool:
    """单条动态是否对当前用户可见（作者本人与管理员始终可见）。

    mutual 可由调用方预先算好传入，避免列表场景逐条重复查询好友集合。
    """
    if user is not None and (post.user_id == user.id or user.role == "admin"):
        return True
    vis = post.visibility or "public"
    if vis == "public":
        return True
    if vis == "friends" and user is not None:
        allowed = mutual if mutual is not None else await _mutual_ids(db, user.id)
        return post.user_id in allowed
    return False


async def _serialize(db: AsyncSession, post: Post, user_id: int | None,
                     with_content: bool = True) -> dict:
    liked, collected = await _liked_collected(db, post.id, user_id)
    author = post.author
    data = {
        "id": post.id,
        "title": post.title,
        "city": post.city,
        "location": post.location,
        "images": _loads(post.images),
        "tags": _loads(post.tags),
        "like_count": post.like_count,
        "collect_count": post.collect_count,
        "comment_count": post.comment_count,
        "view_count": post.view_count,
        "heat": post.heat,
        "status": post.status,
        "visibility": post.visibility or "public",
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "author": {
            "id": author.id if author else 0,
            "nickname": (author.nickname or author.username) if author else "匿名",
            "avatar": author.avatar if author else "",
        },
        "liked": liked,
        "collected": collected,
    }
    if with_content:
        summary = post.content
        data["content"] = summary
        data["excerpt"] = summary[:80] + ("…" if len(summary) > 80 else "")
    else:
        data["excerpt"] = post.content[:80] + ("…" if len(post.content) > 80 else "")
    return data


async def _owned_post(db: AsyncSession, post_id: int) -> Post:
    post = await db.get(Post, post_id)
    if post is None:
        raise NotFoundError("动态不存在")
    return post


@router.get("")
async def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(9, ge=1, le=30),
    city: str | None = None,
    sort: str = Query("new", pattern="^(new|hot)$"),
    mine: bool = False,
    author_id: int | None = None,
    user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    base = select(Post).where(Post.status == "published")
    if city:
        base = base.where(Post.city == city)
    if mine and user:
        base = select(Post).where(Post.user_id == user.id)
    if author_id is not None:
        # 他人主页：只看已发布动态；看自己的主页时连同草稿一并展示
        if user and author_id == user.id:
            base = select(Post).where(Post.user_id == author_id)
        else:
            base = select(Post).where(Post.user_id == author_id, Post.status == "published")
    # 可见范围过滤：
    # - 广场流（无 mine / author_id）：只展示「全部可见」的动态，作者本人也不例外；
    # - 他人主页：公开 + （互关时）好友可见；
    # - 自己主页 / mine：自己的内容全部可见（含好友可见、仅自己可见）。
    self_view = bool((mine and user) or (author_id is not None and user and author_id == user.id))
    mutual = await _mutual_ids(db, user.id) if user else set()
    if self_view:
        clause = None
    elif author_id is not None:
        clause = _visibility_clause(user, mutual)
    else:
        clause = Post.visibility == "public"
    if clause is not None:
        base = base.where(clause)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    order = ((Post.heat.desc(), Post.created_at.desc()) if sort == "hot"
             else (Post.created_at.desc(),))
    rows = (await db.scalars(
        base.order_by(*order).offset((page - 1) * page_size).limit(page_size))).all()
    items = [await _serialize(db, p, user.id if user else None, with_content=False) for p in rows]
    return ok({"items": items, "page": page, "page_size": page_size, "total": total})


@router.get("/cities")
async def post_cities(db: AsyncSession = Depends(get_session)):
    # 城市聚合只统计「全部可见」的动态，避免泄露私密/好友内容的城市信息
    rows = (await db.execute(
        select(Post.city, func.count())
        .where(Post.status == "published", Post.visibility == "public")
        .group_by(Post.city).order_by(func.count().desc()))).all()
    return ok([{"city": c, "count": n} for c, n in rows if c])


@router.get("/friends")
async def friends_feed(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """动态流：我关注的人 + 我自己的动态（含自己的草稿，便于就地管理）。

    好友（互关）才能看到对方的「好友可见」动态；只关注未见回关时仅能看到其公开动态。
    """
    from ...db.models import Follow
    following = (await db.scalars(
        select(Follow.following_id).where(Follow.follower_id == user.id))).all()
    followers = await db.scalar(
        select(func.count()).select_from(Follow)
        .where(Follow.following_id == user.id)) or 0
    mutual = await _mutual_ids(db, user.id)
    ids = [user.id, *[i for i in following if i != user.id]]
    base = select(Post).where(
        Post.user_id.in_(ids),
        or_(Post.status == "published", Post.user_id == user.id),
    )
    clause = _visibility_clause(user, mutual)
    if clause is not None:
        base = base.where(clause)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (await db.scalars(
        base.order_by(Post.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    return ok({"items": [await _serialize(db, p, user.id) for p in rows],
               "page": page, "page_size": page_size, "total": total,
               "following_count": len(following),
               "friends_count": len(mutual),
               "followers_count": int(followers)})


@router.get("/{post_id}")
async def get_post(post_id: int, user: User | None = Depends(get_current_user),
                   db: AsyncSession = Depends(get_session)):
    post = await _owned_post(db, post_id)
    # 无权查看的私密/好友动态一律按「不存在」处理，不泄露其存在性
    if not await _can_view(db, post, user):
        raise NotFoundError("动态不存在")
    post.view_count += 1
    await db.commit()
    data = await _serialize(db, post, user.id if user else None)
    rows = (await db.scalars(
        select(Comment).where(Comment.post_id == post_id).order_by(Comment.created_at))).all()
    data["comments"] = [{
        "id": c.id, "content": c.content,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "user_id": c.user_id,
        "author": {
            "id": c.author.id if c.author else 0,
            "nickname": (c.author.nickname or c.author.username) if c.author else "匿名",
            "avatar": c.author.avatar if c.author else "",
        },
    } for c in rows]
    return ok(data)


@router.post("")
async def create_post(payload: PostIn, user: User = Depends(require_active_user),
                      db: AsyncSession = Depends(get_session)):
    if not payload.content.strip():
        raise ValidationError("动态内容不能为空")
    # 配图统一落到后端资源文件夹：data: URL / 外链先落盘，本地磁盘路径直接丢弃
    from ..media_service.router import materialize_images
    images = await materialize_images(db, payload.images, owner_id=user.id)
    post = Post(
        user_id=user.id, title=payload.title[:160], content=payload.content,
        city=payload.city, location=payload.location,
        images=json.dumps(images, ensure_ascii=False),
        tags=json.dumps(payload.tags, ensure_ascii=False),
        status="published", visibility=payload.visibility,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return ok(await _serialize(db, post, user.id))


@router.put("/{post_id}")
async def update_post(post_id: int, payload: PostIn,
                      user: User = Depends(require_active_user),
                      db: AsyncSession = Depends(get_session)):
    post = await _owned_post(db, post_id)
    if post.user_id != user.id and user.role != "admin":
        raise ForbiddenError("只能编辑自己的动态")
    from ..media_service.router import materialize_images
    images = await materialize_images(db, payload.images, owner_id=post.user_id)
    post.title = payload.title[:160]
    post.content = payload.content
    post.city = payload.city
    post.location = payload.location
    post.images = json.dumps(images, ensure_ascii=False)
    post.tags = json.dumps(payload.tags, ensure_ascii=False)
    post.visibility = payload.visibility
    await db.commit()
    await db.refresh(post)
    return ok(await _serialize(db, post, user.id))


@router.delete("/{post_id}")
async def delete_post(post_id: int, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_session)):
    post = await _owned_post(db, post_id)
    if post.user_id != user.id and user.role != "admin":
        raise ForbiddenError("只能删除自己的动态")
    await db.delete(post)
    await db.commit()
    return ok({"deleted": post_id})


@router.post("/{post_id}/like")
async def toggle_like(post_id: int, user: User = Depends(require_active_user),
                      db: AsyncSession = Depends(get_session)):
    """点赞 / 取消点赞（含热度值 heat 的计数规则）。

    热度规则：同一用户对同一条动态的赞只计一次——首次点赞 heat+1；
    取消点赞 heat-1；取消后再次点赞 heat 不变（无效，不重复累加）。
    因此点赞记录用 active 标记做软删除，而不是直接删行。
    """
    post = await _owned_post(db, post_id)
    if not await _can_view(db, post, user):
        raise NotFoundError("动态不存在")
    row = await db.scalar(select(PostLike).where(
        PostLike.post_id == post_id, PostLike.user_id == user.id))
    if row is None:
        db.add(PostLike(post_id=post_id, user_id=user.id, active=1))
        post.like_count += 1
        post.heat += 1
        liked = True
        # 消息中心：通知动态作者「谁赞了你」
        await notify(db, user_id=post.user_id, kind="like",
                     title=f"{(user.nickname or user.username)} 赞了你的动态",
                     content=post.title, actor_id=user.id, post_id=post.id,
                     link=f"/feed/{post.id}")
    elif row.active:
        row.active = 0
        post.like_count = max(0, post.like_count - 1)
        post.heat = max(0, post.heat - 1)
        liked = False
    else:
        row.active = 1                      # 取消后再次点赞：热度不重复累加
        post.like_count += 1
        liked = True
    await db.commit()
    return ok({"liked": liked, "like_count": post.like_count, "heat": post.heat})


@router.post("/{post_id}/collect")
async def toggle_collect(post_id: int, user: User = Depends(require_active_user),
                         db: AsyncSession = Depends(get_session)):
    post = await _owned_post(db, post_id)
    if not await _can_view(db, post, user):
        raise NotFoundError("动态不存在")
    row = await db.scalar(select(PostCollect).where(
        PostCollect.post_id == post_id, PostCollect.user_id == user.id))
    if row:
        await db.delete(row)
        post.collect_count = max(0, post.collect_count - 1)
        post.heat = max(0, post.heat - 1)
        collected = False
    else:
        db.add(PostCollect(post_id=post_id, user_id=user.id))
        post.collect_count += 1
        post.heat += 1                     # 收藏：热度 +1
        collected = True
        # 收藏成功的回执消息（发给自己；actor_id 为空，不做「不给自己发」过滤）
        await notify(db, user_id=user.id, kind="collect",
                     title="收藏成功", content=post.title,
                     post_id=post.id, link=f"/feed/{post.id}")
        # 通知动态作者「谁收藏了你的动态」
        await notify(db, user_id=post.user_id, kind="collect",
                     title=f"{(user.nickname or user.username)} 收藏了你的动态",
                     content=post.title, actor_id=user.id,
                     post_id=post.id, link=f"/feed/{post.id}")
    await db.commit()
    return ok({"collected": collected, "collect_count": post.collect_count,
               "heat": post.heat})


@router.post("/{post_id}/comments")
async def add_comment(post_id: int, payload: CommentIn,
                      user: User = Depends(require_active_user),
                      db: AsyncSession = Depends(get_session)):
    post = await _owned_post(db, post_id)
    if not await _can_view(db, post, user):
        raise NotFoundError("动态不存在")
    if not payload.content.strip():
        raise ValidationError("留言不能为空")
    comment = Comment(post_id=post_id, user_id=user.id,
                      content=payload.content[:1000], parent_id=payload.parent_id)
    db.add(comment)
    post.comment_count += 1
    post.heat += 1                         # 收到评论：热度 +1
    who = user.nickname or user.username
    snippet = payload.content[:60]
    # 通知动态作者
    await notify(db, user_id=post.user_id, kind="comment",
                 title=f"{who} 评论了你的动态", content=snippet,
                 actor_id=user.id, post_id=post.id, link=f"/feed/{post.id}")
    # 若是回复某条留言，再通知被回复者
    if payload.parent_id:
        parent = await db.get(Comment, payload.parent_id)
        if parent and parent.user_id != post.user_id:
            await notify(db, user_id=parent.user_id, kind="reply",
                         title=f"{who} 回复了你的留言", content=snippet,
                         actor_id=user.id, post_id=post.id, link=f"/feed/{post.id}")
    await db.commit()
    await db.refresh(comment)
    return ok({
        "id": comment.id, "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "user_id": user.id,
        "author": {"id": user.id, "nickname": user.nickname or user.username,
                   "avatar": user.avatar},
    })


@router.put("/comments/{comment_id}")
async def update_comment(comment_id: int, payload: CommentIn,
                         user: User = Depends(require_active_user),
                         db: AsyncSession = Depends(get_session)):
    """编辑自己的留言（内容修改，热度值不受影响）。"""
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError("留言不存在")
    if comment.user_id != user.id and user.role != "admin":
        raise ForbiddenError("只能编辑自己的留言")
    if not payload.content.strip():
        raise ValidationError("留言不能为空")
    comment.content = payload.content[:1000]
    await db.commit()
    await db.refresh(comment)
    return ok({
        "id": comment.id, "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "user_id": comment.user_id,
    })


@router.delete("/comments/{comment_id}")
async def delete_comment(comment_id: int, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_session)):
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError("留言不存在")
    if comment.user_id != user.id and user.role != "admin":
        raise ForbiddenError("只能删除自己的留言")
    post = await db.get(Post, comment.post_id)
    if post:
        post.comment_count = max(0, post.comment_count - 1)
        post.heat = max(0, post.heat - 1)          # 删除评论：热度回退 1
    await db.delete(comment)
    await db.commit()
    return ok({"deleted": comment_id})


@router.get("/mine/collections")
async def my_collections(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_session)):
    mutual = await _mutual_ids(db, user.id)
    stmt = (select(Post).join(PostCollect, PostCollect.post_id == Post.id)
            .where(PostCollect.user_id == user.id))
    clause = _visibility_clause(user, mutual)
    if clause is not None:
        stmt = stmt.where(clause)          # 作者改为私密/好友可见后，不再出现在收藏夹
    rows = (await db.scalars(
        stmt.order_by(PostCollect.created_at.desc()))).all()
    return ok([await _serialize(db, p, user.id, with_content=False) for p in rows])


@router.get("/mine/comments")
async def my_comments(user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_session)):
    """我的评论：列出当前用户发表过的留言及其所属动态。"""
    rows = (await db.scalars(
        select(Comment).where(Comment.user_id == user.id)
        .order_by(Comment.created_at.desc()).limit(100))).all()
    mutual = await _mutual_ids(db, user.id)
    out = []
    for c in rows:
        post = await db.get(Post, c.post_id)
        if post is not None and not await _can_view(db, post, user, mutual):
            continue                        # 已不可见的动态不展示其留言
        images = _loads(post.images) if post else []
        out.append({
            "id": c.id,
            "content": c.content,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "post_id": c.post_id,
            "post_title": post.title if post else "（动态已删除）",
            "post_city": post.city if post else "",
            "post_cover": images[0] if images else "",
        })
    return ok(out)


# ─────────────── 管理员：帖子审核与管理 ───────────────

def _ensure_admin(user: User) -> None:
    if user.role != "admin":
        raise ForbiddenError("需要管理员权限")


@admin_router.get("")
async def admin_list_posts(status: str | None = None,
                           visibility: str | None = None,
                           page: int = Query(1, ge=1),
                           page_size: int = Query(20, ge=1, le=50),
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_session)):
    _ensure_admin(user)
    base = select(Post)
    if status:
        base = base.where(Post.status == status)
    if visibility:
        # 管理员可按可见范围筛选审核（与用户端发帖时的三档口径一致）
        if visibility not in ("public", "friends", "private"):
            raise ValidationError("非法可见范围")
        base = base.where(Post.visibility == visibility)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (await db.scalars(
        base.order_by(Post.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    return ok({"items": [await _serialize(db, p, user.id) for p in rows],
               "total": total, "page": page, "page_size": page_size})


@admin_router.put("/{post_id}/status")
async def admin_set_status(post_id: int, status: str = Query(...),
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_session)):
    _ensure_admin(user)
    if status not in ("published", "pending", "rejected"):
        raise ValidationError("非法状态")
    post = await _owned_post(db, post_id)
    post.status = status
    await db.commit()
    return ok({"id": post.id, "status": post.status})


@admin_router.delete("/{post_id}")
async def admin_delete_post(post_id: int, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_session)):
    _ensure_admin(user)
    post = await _owned_post(db, post_id)
    await db.delete(post)
    await db.commit()
    return ok({"deleted": post_id})
