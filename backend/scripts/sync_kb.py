"""把 data/knowledge_base.json 的最新语料同步进数据库并重建索引。

- 按 title 去重：已存在则更新内容与城市，不存在则新增（幂等）；
- 完成后调用 retriever.rebuild()，把新内容切片向量化写入向量库。

用法（backend 目录，建议带生产 .env）：
    python scripts/sync_kb.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

DATA = Path(__file__).resolve().parents[1] / "data"


async def main() -> None:
    from sqlalchemy import select
    from app.db.session import SessionLocal, init_db
    from app.db.models import KBDocument

    await init_db()
    docs = json.loads((DATA / "knowledge_base.json").read_text(encoding="utf-8"))
    added = updated = 0
    async with SessionLocal() as db:
        rows = (await db.scalars(select(KBDocument))).all()
        by_title = {r.title: r for r in rows}
        for d in docs:
            title = d.get("title", "")
            if not title:
                continue
            if title in by_title:
                r = by_title[title]
                if r.content != d.get("content", "") or r.city != d.get("city", "通用"):
                    r.city = d.get("city", "通用")
                    r.content = d.get("content", "")
                    updated += 1
            else:
                db.add(KBDocument(city=d.get("city", "通用"), title=title,
                                  content=d.get("content", ""), source="内置语料库（更新）"))
                added += 1
        await db.commit()
    print(f"kb_documents 同步：新增 {added} 篇，更新 {updated} 篇")

    from app.services.agent_service.rag.retriever import retriever
    chunks = await retriever.rebuild()
    print(f"索引重建完成：backend={retriever.backend} chunks={chunks}")


asyncio.run(main())
