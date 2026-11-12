"""生产库迁移：帖子可见范围字段（幂等，可重复执行）。

- posts.visibility  可见范围：public 全部可见 / friends 仅互关好友可见 / private 仅自己可见
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
        if not await _has_column(conn, "posts", "visibility"):
            await conn.execute(text(
                "ALTER TABLE posts ADD COLUMN visibility VARCHAR(16) NOT NULL DEFAULT 'public'"))
            print("posts: added visibility")
        else:
            print("posts: visibility exists")
        # 历史数据统一补为「全部可见」，与旧行为保持一致
        await conn.execute(text(
            "UPDATE posts SET visibility='public' WHERE visibility IS NULL OR visibility=''"))
        print("posts: backfilled visibility=public")

    await engine.dispose()
    print("done")


asyncio.run(main())
