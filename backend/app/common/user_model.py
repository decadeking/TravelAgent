"""用户级模型配置：用户只需填自己的 API Key，其余为固定配置。

安全：密钥以密文（Fernet）落库，读取时解密；对外只回传「是否已配置」。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import UserModelConfig
from .crypto import decrypt_secret, encrypt_secret


async def get_user_model_config(db: AsyncSession, user_id: int) -> dict:
    row = await db.get(UserModelConfig, user_id)
    if row is None:
        return {"api_key": "", "model": "", "has_api_key": False}
    key = decrypt_secret(row.api_key)
    return {"api_key": key, "model": row.model or "",
            "has_api_key": bool(key)}


async def save_user_model_config(db: AsyncSession, user_id: int, *,
                                 api_key: str | None = None,
                                 model: str | None = None,
                                 clear_api_key: bool = False) -> dict:
    row = await db.get(UserModelConfig, user_id)
    if row is None:
        row = UserModelConfig(user_id=user_id)
        db.add(row)
    if clear_api_key:
        row.api_key = ""
    elif api_key:                    # 空串表示不修改
        row.api_key = encrypt_secret(api_key.strip())     # 加密落库，不存明文
    if model:
        row.model = model.strip()
    await db.commit()
    await db.refresh(row)
    key = decrypt_secret(row.api_key)
    return {"api_key": key, "model": row.model or "",
            "has_api_key": bool(key)}
