"""旅行吧（社交动态）Schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PostIn(BaseModel):
    title: str = Field(default="", max_length=160)
    content: str = Field(default="", max_length=5000)
    city: str = Field(default="", max_length=64)
    location: str = Field(default="", max_length=128)
    images: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # 可见范围：public 全部可见 / friends 仅互关好友可见 / private 仅自己可见
    visibility: str = Field(default="public", pattern="^(public|friends|private)$")


class CommentIn(BaseModel):
    content: str = Field(max_length=1000)
    parent_id: int | None = None
