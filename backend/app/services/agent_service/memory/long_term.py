"""长期记忆：对话中表达的稳定偏好回写 user_preferences 表。

例如用户说过「不想爬山」，之后每次规划自动注入 system prompt。
这是「记忆层」最直观、最易演示的形态。
"""
from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.models import UserPreference

# 从自然语言里抽取稳定偏好的规则
_PREF_RULES: list[tuple[str, str, str]] = [
    (r"不想爬山|不要爬山|怕累|不想徒步|避免登山", "avoid_hiking", "是"),
    (r"带小孩|带孩子|亲子|小朋友", "family_friendly", "是"),
    (r"带老人|父母|长辈", "with_elderly", "是"),
    (r"情侣|蜜月|二人", "couple", "是"),
    (r"美食|吃货|小吃", "foodie", "是"),
    (r"人文|历史|文化", "culture", "是"),
    (r"自然|风景|户外", "nature", "是"),
    (r"购物|买买买|逛街", "shopping", "是"),
    (r"穷游|省钱|便宜|预算有限", "budget_style", "budget"),
    (r"豪华|高端|享受", "budget_style", "luxury"),
    (r"温泉", "hot_spring", "是"),
]

_PREF_LABEL = {
    "avoid_hiking": "不安排高强度登山",
    "family_friendly": "适合亲子",
    "with_elderly": "照顾老人节奏",
    "couple": "情侣友好",
    "foodie": "重视美食体验",
    "culture": "偏好人文历史",
    "nature": "偏好自然风光",
    "shopping": "偏好购物街区",
    "budget_style": "预算档位",
    "hot_spring": "偏好温泉",
}


async def load_preferences(db: AsyncSession, user_id: int) -> dict[str, str]:
    rows = (await db.scalars(
        select(UserPreference).where(UserPreference.user_id == user_id))).all()
    return {r.pref_key: r.pref_value for r in rows}


async def save_preferences(db: AsyncSession, user_id: int, prefs: dict[str, str]) -> None:
    for k, v in prefs.items():
        existing = await db.scalar(
            select(UserPreference).where(
                UserPreference.user_id == user_id, UserPreference.pref_key == k))
        if existing:
            existing.pref_value = str(v)[:255]
        else:
            db.add(UserPreference(user_id=user_id, pref_key=k[:64], pref_value=str(v)[:255]))
    await db.commit()


def extract_preferences(text: str) -> dict[str, str]:
    """从用户消息中抽取需要长期记忆的偏好。"""
    found: dict[str, str] = {}
    for pattern, key, value in _PREF_RULES:
        if re.search(pattern, text):
            found[key] = value
    return found


def describe_preferences(prefs: dict[str, str]) -> str:
    parts = []
    for k, v in prefs.items():
        label = _PREF_LABEL.get(k, k)
        if k == "budget_style":
            parts.append(f"预算档位：{'经济' if v == 'budget' else '豪华'}")
        else:
            parts.append(label)
    return "；".join(parts) if parts else "无特别偏好"
