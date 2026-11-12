"""生产库迁移：行程出发日期 + 提醒桌面通知标记（幂等，可重复执行）。

create_all 不会给已存在的表加列，因此这里显式 ALTER：
- trips.start_date      出发日期（YYYY-MM-DD），用于开启出发提醒
- reminders.desktop     1 表示触发时同时弹桌面通知（desktop-notification）
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

        for table, col, ddl in (
            ("trips", "start_date",
             "ALTER TABLE trips ADD COLUMN start_date VARCHAR(16) NOT NULL DEFAULT ''"),
            ("reminders", "desktop",
             "ALTER TABLE reminders ADD COLUMN desktop INT NOT NULL DEFAULT 0"),
        ):
            if not await _has_column(conn, table, col):
                await conn.execute(text(ddl))
                print(f"{table}: added {col}")
            else:
                print(f"{table}: {col} exists")

    await engine.dispose()
    print("done")


asyncio.run(main())
