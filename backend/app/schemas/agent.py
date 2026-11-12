"""Agent 对话与行程草稿相关 Schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(max_length=2000)
    request_id: str = Field(description="前端生成的 UUID，用于幂等")
    model: str | None = Field(default=None, description="选择的模型 id，为空则用默认模型")
    tools: list[str] | None = Field(
        default=None,
        description="本次对话启用的工具名白名单，为空表示全部启用（完全访问）")


class Slots(BaseModel):
    destination: str = ""
    days: int = 0
    budget: float = 0.0
    preferences: list[str] = Field(default_factory=list)
    companions: str = ""
    pace: str = "normal"

    def missing(self) -> list[str]:
        miss = []
        if not self.destination:
            miss.append("destination")
        if not self.days:
            miss.append("days")
        if not self.budget:
            miss.append("budget")
        return miss


class PlanItem(BaseModel):
    time_slot: str = "morning"
    poi_name: str = ""
    category: str = "sightseeing"
    cost: float = 0.0
    duration_min: int = 120
    note: str = ""


class PlanDay(BaseModel):
    day_no: int
    city: str = ""
    weather: str = ""
    items: list[PlanItem] = Field(default_factory=list)
    day_cost: float = 0.0


class PlanDraft(BaseModel):
    title: str = ""
    destination: str = ""
    days: int = 0
    budget: float = 0.0
    total_cost: float = 0.0
    within_budget: bool = True
    day_list: list[PlanDay] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SessionOut(BaseModel):
    session_id: str
    summary: str = ""
    messages: list[dict] = Field(default_factory=list)
    slots: dict = Field(default_factory=dict)
    plan_draft: dict | None = None
    revision_count: int = 0
    status: str = "active"
    can_resume: bool = True
