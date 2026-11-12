"""检索器：语料加载 → 切片 → 向量化 → 入库 → top-k 检索。

- 语料来源：数据库 kb_documents（管理员可增删改，可重建索引）；
  若库为空则回落到内置 data/knowledge_base.json。
- 切片参数、top-k、阈值、Embedding 提供方、向量库后端均取自运行时配置。
- 两级过滤：先按城市元数据过滤，再按相似度阈值剔除。
- 向量库双后端：VECTOR_BACKEND=pgvector 用 PostgreSQL+pgvector（HNSW）；
  pgvector 不可用时自动回落到内存实现，保证 RAG 链路不中断。
"""
from __future__ import annotations

import json
from pathlib import Path

from ....common.config import settings
from ....common.logging import get_logger
from ....common.runtime_config import runtime_config
from .chunker import chunk_documents
from .embeddings import Embedder
from .pgvector_store import PgVectorStore
from .store import InMemoryVectorStore

logger = get_logger("rag")
_DATA_DIR = Path(__file__).resolve().parents[4] / "data"


def _async_size(store) -> int:
    return store.size()


class Retriever:
    def __init__(self) -> None:
        self.store = InMemoryVectorStore()
        self.backend = "memory"
        self._ready = False
        self._chunk_count = 0

    async def _load_docs(self) -> list[dict]:
        docs: list[dict] = []
        try:
            from sqlalchemy import select

            from ....db.models import KBDocument
            from ....db.session import SessionLocal
            async with SessionLocal() as db:
                rows = (await db.scalars(select(KBDocument))).all()
                docs = [{"city": r.city, "title": r.title, "content": r.content} for r in rows]
        except Exception:
            logger.warning("从数据库加载知识库失败，回落内置语料", extra={"tool": "kb"})
        if not docs:
            try:
                with open(_DATA_DIR / "knowledge_base.json", encoding="utf-8") as f:
                    docs = json.load(f)
            except Exception:
                docs = []
        return docs

    async def _make_store(self, cfg: dict):
        """按配置构建向量库后端；pgvector 失败自动回落内存。"""
        backend = cfg.get("vector_backend") or settings.vector_backend
        embedder = Embedder(
            provider=cfg.get("embedding_provider"),
            dim=int(cfg.get("embedding_dim") or settings.embedding_dim),
            model=cfg.get("embedding_model"),
        )
        if backend == "pgvector":
            try:
                store = PgVectorStore(
                    dsn=cfg.get("vector_db_url") or settings.vector_db_url,
                    embedder=embedder,
                    ef_search=int(cfg.get("vector_hnsw_ef_search")
                                  or settings.vector_hnsw_ef_search),
                )
                await store._ensure_schema(embedder.dim)   # 探活 + 建表
                self.backend = "pgvector"
                return store
            except Exception as exc:
                logger.warning("pgvector 不可用，回落内存向量库: %s", exc)
        self.backend = "memory"
        store = InMemoryVectorStore(embedder=embedder)
        return store

    async def rebuild(self) -> int:
        """重建索引：清空后按当前配置重新切片、向量化、入库。"""
        cfg = await runtime_config.get_rag()
        self.store = await self._make_store(cfg)
        await self.store.reset()
        docs = await self._load_docs()
        chunks = chunk_documents(
            docs,
            chunk_size=int(cfg.get("chunk_size", 380)),
            overlap=int(cfg.get("chunk_overlap", 50)),
        )
        await self.store.add(chunks)
        self._chunk_count = len(chunks)
        self._ready = True
        logger.info("知识库索引重建完成",
                    extra={"tool": f"backend={self.backend} chunks={self._chunk_count}"})
        return self._chunk_count

    async def ensure_ready(self) -> None:
        if not self._ready:
            await self.rebuild()

    @staticmethod
    def rewrite_query(query: str) -> str:
        """查询改写（Q20）：口语化 → 检索友好形式。

        规则式改写零依赖、可解释；「带娃去哪好玩」→「亲子 景点」。
        """
        rewrites = {
            "带娃": "亲子", "小孩": "亲子", "孩子": "亲子", "宝宝": "亲子",
            "好玩": "景点", "好玩的地方": "景点", "去哪": "景点 推荐",
            "吃什么": "美食", "吃啥": "美食", "好吃的": "美食",
            "便宜": "省钱 门票", "省钱": "经济 门票",
            "累": "休闲 节奏", "老人": "舒适 节奏",
            "避坑": "提示 注意", "坑": "提示 注意",
        }
        q = query
        for k, v in rewrites.items():
            if k in q:
                q = q.replace(k, v)
        return q

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        """词法相关度（重排用）：查询字符 bigram 在块中的覆盖率。

        近似 cross-encoder 的「查询-文档联合打分」思路——双塔向量相似度
        对关键词不敏感，词法分可把真正包含答案的块排到前面。
        """
        qs = {query[i:i + 2] for i in range(len(query) - 1)}
        if not qs:
            return 0.0
        hit = sum(1 for g in qs if g in text)
        return hit / len(qs)

    async def retrieve(self, query: str, city: str | None = None,
                       topk: int | None = None) -> list[dict]:
        cfg = await runtime_config.get_rag()
        if not cfg.get("enabled", True):
            return []
        await self.ensure_ready()
        k = topk or int(cfg.get("topk", 5))
        threshold = float(cfg.get("score_threshold", 0.5))
        # 查询改写 + 粗召回 top-20 + 词法/向量混合精排取 top-k
        rq = self.rewrite_query(query)
        candidates = await self.store.search(rq, topk=max(k * 4, 20), city=city or None,
                                             threshold=threshold)
        if not candidates:
            candidates = await self.store.search(rq, topk=max(k * 4, 20),
                                                 city=city or None, threshold=0.0)
        rerank = bool(cfg.get("rerank", True))
        if rerank and candidates:
            for h in candidates:
                lex = self._lexical_score(rq, h.text) + self._lexical_score(rq, h.metadata.get("title", ""))
                h.score = 0.6 * h.score + 0.4 * lex
            candidates.sort(key=lambda h: -h.score)
        hits = candidates[:k]
        return [
            {"chunk_id": h.chunk_id, "text": h.text, "score": round(h.score, 4),
             "city": h.metadata.get("city", ""), "title": h.metadata.get("title", ""),
             "source": h.metadata.get("source", "")}
            for h in hits
        ]

    async def search_kb(self, query: str, city: str = "") -> dict:
        items = await self.retrieve(query, city=city or None)
        return {"query": query, "items": [{"title": i["title"], "snippet": i["text"][:120]}
                                          for i in items]}

    @property
    def chunk_count(self) -> int:
        return self._chunk_count


retriever = Retriever()
