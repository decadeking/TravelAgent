"""pgvector 向量存储（RAG 生产形态）。

- 表结构：kb_chunks(doc_id, city, title, chunk_index, text, embedding vector(D))
- 索引：HNSW（m=16, ef_construction=64，对齐面试手册 Q19）+ 城市元数据索引
- 检索：先按城市过滤、再向量近邻（cosine 距离），ef_search 可调
- 维度自适应：embedding 模型换维度时自动重建表（知识库规模小，重建秒级）

接口与 InMemoryVectorStore 同构（add / search / size / reset），
通过 VECTOR_BACKEND 环境变量或运行时配置切换，业务代码零改动。
"""
from __future__ import annotations

from dataclasses import dataclass

from .chunker import Chunk
from .embeddings import Embedder


@dataclass
class SearchHit:
    chunk_id: str
    text: str
    metadata: dict
    score: float


class PgVectorStore:
    def __init__(self, dsn: str, embedder: Embedder | None = None,
                 ef_search: int = 40) -> None:
        self.dsn = dsn
        self.embedder = embedder or Embedder()
        self.ef_search = ef_search
        self._pool = None
        self._ready = False

    async def _conn(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        return self._pool

    async def _ensure_schema(self, dim: int) -> None:
        """建表/索引；embedding 维度与配置不一致时重建。"""
        pool = await self._conn()
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            row = await conn.fetchrow(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'kb_chunks'::regclass AND attname = 'embedding'")
            current_dim = (row["atttypmod"] if row else None)
            if row is not None and current_dim == dim:
                self._ready = True
                return
            # 首次或维度变化：重建表与 HNSW 索引
            await conn.execute("DROP TABLE IF EXISTS kb_chunks CASCADE")
            await conn.execute(
                f"CREATE TABLE kb_chunks ("
                f"  id BIGSERIAL PRIMARY KEY,"
                f"  doc_id BIGINT NOT NULL DEFAULT 0,"
                f"  city TEXT NOT NULL DEFAULT '',"
                f"  title TEXT NOT NULL DEFAULT '',"
                f"  chunk_index INT NOT NULL DEFAULT 0,"
                f"  text TEXT NOT NULL,"
                f"  embedding vector({dim}) NOT NULL,"
                f"  created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kb_chunks_city ON kb_chunks (city)")
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_kb_chunks_hnsw ON kb_chunks "
                "USING hnsw (embedding vector_cosine_ops) "
                "WITH (m = 16, ef_construction = 64)")
            self._ready = True

    async def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        vectors = await self.embedder.embed([c.text for c in chunks])
        await self._ensure_schema(len(vectors[0]))
        pool = await self._conn()
        async with pool.acquire() as conn:
            rows = [
                (c.metadata.get("doc_id", ""), c.metadata.get("city", ""),
                 c.metadata.get("title", ""), i, c.text,
                 "[" + ",".join(str(x) for x in vec) + "]")
                for i, (c, vec) in enumerate(zip(chunks, vectors))
            ]

            def _doc_num(doc_id: str) -> int:
                digits = "".join(ch for ch in str(doc_id) if ch.isdigit())
                return int(digits) if digits else 0

            await conn.executemany(
                "INSERT INTO kb_chunks(doc_id, city, title, chunk_index, text, embedding) "
                "VALUES ($1::bigint, $2, $3, $4, $5, $6::vector)",
                [(_doc_num(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows],
            )

    async def search(self, query: str, *, topk: int = 5, city: str | None = None,
                     threshold: float = 0.0) -> list[SearchHit]:
        qv = (await self.embedder.embed([query], is_query=True))[0]
        await self._ensure_schema(len(qv))
        pool = await self._conn()
        vec_literal = "[" + ",".join(str(x) for x in qv) + "]"
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL hnsw.ef_search = {int(self.ef_search)}")
                if city:
                    rows = await conn.fetch(
                        "SELECT text, city, title, chunk_index, "
                        "       1 - (embedding <=> $1::vector) AS score "
                        "FROM kb_chunks "
                        "WHERE (city = $2 OR city = '通用') AND 1 - (embedding <=> $1::vector) >= $3 "
                        "ORDER BY embedding <=> $1::vector LIMIT $4",
                        vec_literal, city, threshold, topk)
                else:
                    rows = await conn.fetch(
                        "SELECT text, city, title, chunk_index, "
                        "       1 - (embedding <=> $1::vector) AS score "
                        "FROM kb_chunks "
                        "WHERE 1 - (embedding <=> $1::vector) >= $2 "
                        "ORDER BY embedding <=> $1::vector LIMIT $3",
                        vec_literal, threshold, topk)
        return [
            SearchHit(chunk_id=f"{r['title']}#{r['chunk_index']}", text=r["text"],
                      metadata={"city": r["city"], "title": r["title"]},
                      score=float(r["score"]))
            for r in rows
        ]

    async def _current_dim(self):
        pool = await self._conn()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'kb_chunks'::regclass AND attname = 'embedding'")
            return row["atttypmod"] if row else None

    async def size(self) -> int:
        try:
            pool = await self._conn()
            async with pool.acquire() as conn:
                return await conn.fetchval("SELECT COUNT(*) FROM kb_chunks")
        except Exception:
            return 0

    async def reset(self) -> None:
        try:
            pool = await self._conn()
            async with pool.acquire() as conn:
                await conn.execute("TRUNCATE TABLE kb_chunks RESTART IDENTITY")
        except Exception:
            pass

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
