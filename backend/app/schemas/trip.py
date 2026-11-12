"""行程 CRUD 相关 Schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ItemIn(BaseModel):
    seq: int = 1
    time_slot: str = "morning"
    poi_name: str
    category: str = "sightseeing"
    cost: float = 0.0
    duration_min: int = 120
    note: str = ""


class DayIn(BaseModel):
    day_no: int
    city: str = ""
    weather_snapshot: str = ""
    items: list[ItemIn] = Field(default_factory=list)


class TripCreateIn(BaseModel):
    title: str = Field(max_length=128)
    destination: str
    days: int = 1
    budget: float = 0.0
    remark: str = Field(default="", max_length=1000)   # 旅程备注 / 说明
    start_date: str = Field(default="", max_length=16)  # 出发日期 YYYY-MM-DD（用于开启提醒）
    status: str = "draft"
    day_list: list[DayIn] = Field(default_factory=list)


class TripUpdateIn(BaseModel):
    title: str | None = None
    destination: str | None = None
    days: int | None = None
    budget: float | None = None
    remark: str | None = Field(default=None, max_length=1000)
    start_date: str | None = Field(default=None, max_length=16)
    status: str | None = None
    version: int | None = Field(default=None, description="乐观锁版本号")
    day_list: list[DayIn] | None = None


class ItemOut(BaseModel):
    id: int
    seq: int
    time_slot: str
    poi_name: str
    category: str
    cost: float
    duration_min: int
    note: str

    model_config = {"from_attributes": True}


class DayOut(BaseModel):
    id: int
    day_no: int
    city: str
    weather_snapshot: str
    items: list[ItemOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TripOut(BaseModel):
    id: int
    user_id: int
    title: str
    destination: str
    days: int
    budget: float
    remark: str = ""
    start_date: str = ""
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    day_list: list[DayOut] = Field(default_factory=list)
    total_cost: float = 0.0

    model_config = {"from_attributes": True}


class TripListItem(BaseModel):
    id: int
    title: str
    destination: str
    days: int
    budget: float
    remark: str = ""
    start_date: str = ""
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}
