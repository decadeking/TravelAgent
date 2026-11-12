"""把历史明文密钥升级为密文（幂等，可重复执行）。

覆盖两处存储：
1) user_model_configs.api_key —— 用户级密钥
2) system_settings 的 llm.api_key / rag.embedding_api_key —— 管理员级密钥
同时把 api_key 列宽从 VARCHAR(255) 扩到 512（密文比明文长）。

用法（backend 目录）：python scripts/encrypt_existing_keys.py
"""
import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.common.crypto import encrypt_secret, is_encrypted  # noqa: E402


async def main() -> None:
    from sqlalchemy import text
    from app.db.session import engine

    changed_users = 0
    async with engine.begin() as conn:
        dialect = conn.dialect.name
        if dialect == "mysql":
            cols = await conn.execute(text(
                "SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='user_model_configs' "
                "AND COLUMN_NAME='api_key'"))
            cur = next((int(r[0]) for r in cols if r[0]), None)
            if cur is not None and cur < 512:
                await conn.execute(text(
                    "ALTER TABLE user_model_configs MODIFY api_key VARCHAR(512) NOT NULL DEFAULT ''"))
                print(f"widened user_model_configs.api_key: {cur} -> 512")

        rows = await conn.execute(text("SELECT user_id, api_key FROM user_model_configs"))
        for uid, key in list(rows):
            if key and not is_encrypted(key):
                await conn.execute(text(
                    "UPDATE user_model_configs SET api_key=:k WHERE user_id=:u"),
                    {"k": encrypt_secret(key), "u": uid})
                changed_users += 1

        rows = await conn.execute(text("SELECT `key`, value FROM system_settings"))
        for skey, svalue in list(rows):
            try:
                data = json.loads(svalue)
            except Exception:
                continue
            field = {"llm": "api_key", "rag": "embedding_api_key"}.get(skey)
            if not field:
                continue
            if data.get(field) and not is_encrypted(data[field]):
                data[field] = encrypt_secret(data[field])
                await conn.execute(text(
                    "UPDATE system_settings SET value=:v WHERE `key`=:k"),
                    {"v": json.dumps(data, ensure_ascii=False), "k": skey})
                print(f"encrypted system_settings.{skey}.{field}")
    await engine.dispose()
    print(f"done. users upgraded: {changed_users}")


asyncio.run(main())
