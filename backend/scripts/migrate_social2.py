"""生产库迁移：动态热度 + 点赞软删除 + 动态页背景图（幂等，可重复执行）。

- posts.heat         热度值（评论/收藏各 +1，点赞每人只计一次）
- post_likes.active  1=已点赞 / 0=已取消（保留记录，保证取消再赞不重复加热度）
- users.cover        动态页背景图（后端资源路径）
并按「点赞数 + 收藏数 + 评论数」回填一次 heat 基线。
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
            ("posts", "heat", "ALTER TABLE posts ADD COLUMN heat INT NOT NULL DEFAULT 0"),
            ("post_likes", "active",
             "ALTER TABLE post_likes ADD COLUMN active TINYINT NOT NULL DEFAULT 1"),
            ("users", "cover", "ALTER TABLE users ADD COLUMN cover VARCHAR(255) NOT NULL DEFAULT ''"),
        ):
            if not await _has_column(conn, table, col):
                await conn.execute(text(ddl))
                print(f"{table}: added {col}")
            else:
                print(f"{table}: {col} exists")

        # 热度基线回填（只对尚未计算过的 0 值生效，避免重复累加）
        await conn.execute(text(
            "UPDATE posts SET heat = like_count + collect_count + comment_count "
            "WHERE heat = 0 AND (like_count + collect_count + comment_count) > 0"))
        print("posts: heat 基线已回填")

    await engine.dispose()
    print("done")


asyncio.run(main())
