"""SQLAlchemy ORM 模型。

表结构对齐设计文档：行程三级结构（trips → trip_days → itinerary_items），
外加 users / user_preferences（长期记忆回写）/ agent_sessions（会话状态）/
llm_call_logs（模型调用台账）。
默认使用 SQLite；生产可无缝切到 MySQL 8。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(64), default="")
    avatar: Mapped[str] = mapped_column(String(255), default="")
    cover: Mapped[str] = mapped_column(String(255), default="")     # 动态页背景图（后端资源路径）
    role: Mapped[str] = mapped_column(String(16), default="user")   # user | admin
    bio: Mapped[str] = mapped_column(String(255), default="")
    # 黑名单：被管理员拉黑后禁止发布动态、点赞、评论、收藏等社区互动
    banned: Mapped[int] = mapped_column(Integer, default=0)
    ban_reason: Mapped[str] = mapped_column(String(120), default="")
    banned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    preferences: Mapped[list["UserPreference"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class UserPreference(Base):
    """长期偏好记忆回写：对话中表达的稳定偏好回写此表。"""
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", "pref_key", name="uk_user_pref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    pref_key: Mapped[str] = mapped_column(String(64))
    pref_value: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="preferences")


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        Index("idx_trips_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    destination: Mapped[str] = mapped_column(String(64))
    days: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[float] = mapped_column(Float, default=0.0)
    remark: Mapped[str] = mapped_column(Text, default="")            # 旅程备注 / 说明
    start_date: Mapped[str] = mapped_column(String(16), default="")  # 出发日期 YYYY-MM-DD（用于开启提醒）
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|confirmed|shared
    version: Mapped[int] = mapped_column(Integer, default=1)         # 乐观锁
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    user: Mapped[User] = relationship(back_populates="trips")
    day_list: Mapped[list["TripDay"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripDay.day_no")


class TripDay(Base):
    __tablename__ = "trip_days"
    __table_args__ = (UniqueConstraint("trip_id", "day_no", name="uk_trip_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    day_no: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(64), default="")
    weather_snapshot: Mapped[str] = mapped_column(String(255), default="")

    trip: Mapped[Trip] = relationship(back_populates="day_list")
    items: Mapped[list["ItineraryItem"]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="ItineraryItem.seq")


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"
    __table_args__ = (Index("idx_items_day_seq", "day_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("trip_days.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1)
    time_slot: Mapped[str] = mapped_column(String(16), default="morning")  # morning|afternoon|evening
    poi_name: Mapped[str] = mapped_column(String(128))                     # 反范式冗余，列表免连表
    category: Mapped[str] = mapped_column(String(32), default="sightseeing")
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    duration_min: Mapped[int] = mapped_column(Integer, default=120)
    note: Mapped[str] = mapped_column(Text, default="")

    day: Mapped[TripDay] = relationship(back_populates="items")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    state_json: Mapped[str] = mapped_column(Text, default="{}")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"
    __table_args__ = (
        Index("idx_logs_user_created", "user_id", "created_at"),
        Index("idx_logs_trace", "trace_id"),
        UniqueConstraint("request_id", name="uk_logs_request_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str] = mapped_column(String(64), default="")
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    purpose: Mapped[str] = mapped_column(String(32), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ───────────────────── 社交动态（旅行吧） ─────────────────────

class Post(Base):
    """旅行风光动态：图文帖子 + 点赞/收藏/评论计数。"""
    __tablename__ = "posts"
    __table_args__ = (
        Index("idx_posts_status_created", "status", "created_at"),
        Index("idx_posts_user", "user_id"),
        Index("idx_posts_city", "city"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(128), default="")
    images: Mapped[str] = mapped_column(Text, default="[]")   # JSON 数组
    tags: Mapped[str] = mapped_column(Text, default="[]")     # JSON 数组
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    collect_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    heat: Mapped[int] = mapped_column(Integer, default=0)   # 热度值：评论/收藏各 +1，点赞每人只计一次
    status: Mapped[str] = mapped_column(String(16), default="published")  # published|pending|rejected
    # 可见范围：public 全部可见 / friends 仅互关好友可见 / private 仅自己可见
    visibility: Mapped[str] = mapped_column(String(16), default="public")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    author: Mapped[User] = relationship(lazy="selectin")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan", order_by="Comment.created_at")


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (Index("idx_comments_post", "post_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    post: Mapped[Post] = relationship(back_populates="comments")
    author: Mapped[User] = relationship(lazy="selectin")


class PostLike(Base):
    """点赞记录：用 active 做软删除，保证「同一用户的赞只加热度一次」。"""
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uk_post_like"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    active: Mapped[int] = mapped_column(Integer, default=1)   # 1=已点赞，0=已取消（保留记录）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PostCollect(Base):
    __tablename__ = "post_collects"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uk_post_collect"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ───────────────────── 知识库与系统配置 ─────────────────────

class KBDocument(Base):
    """RAG 知识库文档（可由管理员增删改并重建索引）。"""
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(64), default="通用", index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SystemSetting(Base):
    """系统级运行时配置（LLM 模型 / 向量模型 / 知识库参数）。"""
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="{}")   # JSON
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class UserModelConfig(Base):
    """用户级模型配置：只需填自己的 API Key，其余（Base URL/参数）为固定配置。"""
    __tablename__ = "user_model_configs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    api_key: Mapped[str] = mapped_column(String(512), default="")   # 密文存储（Fernet）
    model: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Media(Base):
    """图片资源：二进制文件保存在后端图片文件夹（static/uploads），
    数据库只存元数据与相对路径。风景配图、头像等与业务数据一起在
    MySQL/SQLite 中登记，文件本体落盘，不依赖外部图床。
    """
    __tablename__ = "media"
    __table_args__ = (Index("idx_media_owner", "owner_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="image")   # image | avatar
    filename: Mapped[str] = mapped_column(String(160), default="")
    mime: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    path: Mapped[str] = mapped_column(String(255), default="")       # 相对 static/uploads 的路径
    source_url: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ───────────────────── 行程提醒 / 通知 ─────────────────────

class Reminder(Base):
    """未来行程提醒：智能体识别到「出发前提醒我」时写入，由后台调度器触发。"""
    __tablename__ = "reminders"
    __table_args__ = (
        Index("idx_reminders_due", "status", "remind_at"),
        Index("idx_reminders_user", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    trip_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    remind_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|fired|cancelled
    source: Mapped[str] = mapped_column(String(16), default="agent")    # agent|manual|trip
    desktop: Mapped[int] = mapped_column(Integer, default=0)            # 1=触发时同时弹桌面通知
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Notification(Base):
    """站内消息：提醒触发、他人点赞/评论/回复/关注、收藏成功、Token 超额等。

    kind 取值：reminder | like | comment | reply | follow | collect | token | system
    actor_id/post_id/link 用于前端点击后跳转到对应页面。
    """
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notif_user", "user_id", "created_at"),
        Index("idx_notif_user_kind", "user_id", "kind", "read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="system")
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link: Mapped[str] = mapped_column(String(255), default="")
    read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Follow(Base):
    """关注关系：关注即互为好友（双向建立两条记录）。

    follower_id 关注 following_id；两人互相都存在记录即为好友。
    """
    __tablename__ = "follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uk_follow"),
        Index("idx_follow_follower", "follower_id", "created_at"),
        Index("idx_follow_following", "following_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    following_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
