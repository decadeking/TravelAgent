"""给生产库 llm_call_logs 补 request_id 列与唯一索引（幂等，可重复执行）。"""
import asyncio
import sys

sys.path.insert(0, ".")


async def main() -> None:
    from sqlalchemy import text
    from app.db.session import engine

    async with engine.begin() as conn:
        rows = await conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='llm_call_logs'"))
        cols = {r[0] for r in rows}
        if "request_id" not in cols:
            await conn.execute(text(
                "ALTER TABLE llm_call_logs ADD COLUMN request_id VARCHAR(64) NULL"))
            print("added column request_id")
        idx = await conn.execute(text(
            "SELECT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='llm_call_logs' "
            "AND INDEX_NAME='uk_logs_request_id'"))
        if not list(idx):
            await conn.execute(text(
                "ALTER TABLE llm_call_logs ADD UNIQUE INDEX uk_logs_request_id (request_id)"))
            print("added unique index")
    await engine.dispose()
    print("done")


asyncio.run(main())
