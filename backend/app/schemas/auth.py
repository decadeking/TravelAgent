"""用户 / 鉴权相关 Schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    nickname: str = Field(default="", max_length=32)


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    nickname: str
    avatar: str = ""
    role: str = "user"
    bio: str = ""
    created_at: datetime | None = None


class ProfileUpdateIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=32)
    avatar: str | None = Field(default=None, max_length=512)
    cover: str | None = Field(default=None, max_length=512)
    bio: str | None = Field(default=None, max_length=255)


class ModelConfigIn(BaseModel):
    """用户级模型配置：只暴露密钥与模型选择，其余为固定配置。"""
    api_key: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=64)
    clear_api_key: bool = False


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class PreferenceIn(BaseModel):
    preferences: dict[str, str]


class UsageOut(BaseModel):
    used_tokens: int
    quota: int
    remaining: int
    date: str
