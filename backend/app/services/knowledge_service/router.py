"""knowledge-service：面向普通用户的只读知识库信息。

管理员在「系统设置」里维护向量模型与知识库参数；普通用户不需要改配置，
但需要「看得见」知识库当前状态（是否开放、用哪个向量库、收了多少文档与分块），
因此这里提供一个只读概览接口，供个人设置页展示。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.runtime_config import runtime_config, vector_model_ready
from ...db.models import KBDocument, User
from ...db.session import get_session
from ...gateway.deps import get_current_user
from ...schemas.common import ok

router = APIRouter(prefix="/api/knowledge", tags=["knowledge-service"])


@router.get("/overview")
async def overview(limit: int = Query(8, ge=1, le=30),
                   user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_session)):
    """知识库概览：开放状态、向量库后端、切片/检索参数、最近入库文档。"""
    cfg = await runtime_config.get_rag()
    ready, reason = vector_model_ready(cfg)

    from ..agent_service.rag.retriever import retriever
    chunks = retriever.chunk_count
    backend = retriever.backend
    if not chunks:                       # 首次访问：确保索引已构建，返回真实分块数
        try:
            chunks = await retriever.rebuild()
            backend = retriever.backend
        except Exception:
            chunks = 0

    doc_total = await db.scalar(select(func.count()).select_from(KBDocument)) or 0
    rows = (await db.scalars(
        select(KBDocument).order_by(KBDocument.id.desc()).limit(limit))).all()
    return ok({
        "ready": ready, "reason": reason,
        "enabled": bool(cfg.get("enabled", True)),
        "vector_backend": backend,
        "chunks": chunks,
        "documents": doc_total,
        "embedding": {
            "provider": cfg.get("embedding_provider"),
            "model": cfg.get("embedding_model"),
            "dim": cfg.get("embedding_dim"),
        },
        "chunking": {"size": cfg.get("chunk_size"), "overlap": cfg.get("chunk_overlap")},
        "retrieval": {"topk": cfg.get("topk"), "threshold": cfg.get("score_threshold"),
                      "rerank": bool(cfg.get("rerank", True))},
        "recent": [{
            "id": r.id, "city": r.city or "通用", "title": r.title,
            "chars": len(r.content or ""),
            "source": (r.source or "")[:60],
            "created_at": r.created_at.isoformat(sep=" ", timespec="minutes")
            if r.created_at else None,
        } for r in rows],
    })
