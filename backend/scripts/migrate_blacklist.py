"""生产库迁移：用户黑名单字段（幂等，可重复执行）。

- users.banned      是否被拉黑（1=拉黑）
- users.ban_reason  拉黑原因
- users.banned_at   拉黑时间
"""
import asyncio
import sys

sys.path.insert(0, ".")


async def _has_column(conn, table: str, column: str) -> bool:
    from sqlalchemy import text
    rows = await conn.execute(text(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t AND COLUMN_NAME=:c"),
        {"t": table, "c": column})
    return bool(list(rows))


async def main() -> None:
    from sqlalchemy import text

    from app.db.session import engine

    async with engine.begin() as conn:
        if conn.dialect.name != "mysql":
            print(f"skip alter for dialect={conn.dialect.name}（非 MySQL 由 create_all 建表）")
            await engine.dispose()
            return
        for col, ddl in (
            ("banned", "ALTER TABLE users ADD COLUMN banned TINYINT NOT NULL DEFAULT 0"),
            ("ban_reason", "ALTER TABLE users ADD COLUMN ban_reason VARCHAR(120) NOT NULL DEFAULT ''"),
            ("banned_at", "ALTER TABLE users ADD COLUMN banned_at DATETIME NULL"),
        ):
            if not await _has_column(conn, "users", col):
                await conn.execute(text(ddl))
                print(f"users: added {col}")
            else:
                print(f"users: {col} exists")

    await engine.dispose()
    print("done")


asyncio.run(main())
