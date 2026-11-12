"""向量存储：内存实现（默认）。

真实生产用 PostgreSQL + pgvector（HNSW 索引，m=16、ef_construction=64），
支持「先按城市元数据过滤，再向量检索」。这里提供同构的内存实现，
接口签名与 pgvector 方案对齐，切换时只替换实现。
"""
from __future__ import annotations

from dataclasses import dataclass

from .chunker import Chunk
from .embeddings import Embedder, cosine


@dataclass
class SearchHit:
    chunk_id: str
    text: str
    metadata: dict
    score: float


class InMemoryVectorStore:
    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or Embedder()
        self._vectors: list[list[float]] = []
        self._chunks: list[Chunk] = []

    async def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        vectors = await self.embedder.embed([c.text for c in chunks])
        self._vectors.extend(vectors)
        self._chunks.extend(chunks)

    async def search(self, query: str, *, topk: int = 5, city: str | None = None,
                     threshold: float = 0.0) -> list[SearchHit]:
        if not self._chunks:
            return []
        qv = (await self.embedder.embed([query], is_query=True))[0]
        hits: list[SearchHit] = []
        for vec, chunk in zip(self._vectors, self._chunks):
            if city and chunk.metadata.get("city") not in (city, "通用"):
                continue
            score = cosine(qv, vec)
            if score >= threshold:
                hits.append(SearchHit(chunk.chunk_id, chunk.text, chunk.metadata, score))
        hits.sort(key=lambda h: -h.score)
        return hits[:topk]

    async def size(self) -> int:
        return len(self._chunks)

    async def reset(self) -> None:
        self._vectors.clear()
        self._chunks.clear()
