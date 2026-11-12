"""生产库迁移：消息中心 + 好友关系（幂等，可重复执行）。

- notifications 表补列：kind 索引、actor_id / post_id / link
- 新增 follows 表（关注关系）
create_all 不会给已存在的表加列，因此这里显式 ALTER。
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


async def _has_index(conn, table: str, index: str) -> bool:
    from sqlalchemy import text
    rows = await conn.execute(text(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t AND INDEX_NAME=:i"),
        {"t": table, "i": index})
    return bool(list(rows))


async def main() -> None:
    from sqlalchemy import text
    from app.db.session import engine

    async with engine.begin() as conn:
        dialect = conn.dialect.name
        if dialect != "mysql":
            print(f"skip alter for dialect={dialect}（非 MySQL 由 create_all 建表）")
            await engine.dispose()
            return

        for col, ddl in (
            ("actor_id", "ALTER TABLE notifications ADD COLUMN actor_id INT NULL"),
            ("post_id", "ALTER TABLE notifications ADD COLUMN post_id INT NULL"),
            ("link", "ALTER TABLE notifications ADD COLUMN link VARCHAR(255) NOT NULL DEFAULT ''"),
        ):
            if not await _has_column(conn, "notifications", col):
                await conn.execute(text(ddl))
                print(f"notifications: added {col}")

        if not await _has_index(conn, "notifications", "idx_notif_user_kind"):
            await conn.execute(text(
                "CREATE INDEX idx_notif_user_kind ON notifications (user_id, kind, `read`)"))
            print("notifications: added idx_notif_user_kind")

        # 行程备注 / 旅程说明
        if not await _has_column(conn, "trips", "remark"):
            await conn.execute(text("ALTER TABLE trips ADD COLUMN remark TEXT NULL"))
            print("trips: added remark")

        exists = await conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='follows'"))
        if not list(exists):
            await conn.execute(text(
                "CREATE TABLE follows ("
                "  id INT AUTO_INCREMENT PRIMARY KEY,"
                "  follower_id INT NOT NULL,"
                "  following_id INT NOT NULL,"
                "  created_at DATETIME NOT NULL,"
                "  UNIQUE KEY uk_follow (follower_id, following_id),"
                "  KEY idx_follow_follower (follower_id, created_at),"
                "  KEY idx_follow_following (following_id, created_at)"
                ") DEFAULT CHARSET=utf8mb4"))
            print("created table follows")

    await engine.dispose()
    print("done")


asyncio.run(main())
