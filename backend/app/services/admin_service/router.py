"""admin-service：系统设置（大模型 / 向量模型 / 知识库参数）、知识库管理、
帖子审核入口、可观测性与故障演练。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.circuit_breaker import all_breakers
from ...common.errors import NotFoundError
from ...common.fault import fault
from ...common.metrics import metrics
from ...common.runtime_config import runtime_config
from ...common.tracing import tracer
from ...db.models import KBDocument, Post, Trip, User
from ...db.session import get_session
from ...gateway.deps import require_admin
from ...schemas.common import ok

router = APIRouter(prefix="/api/admin", tags=["admin-service"])


class FaultIn(BaseModel):
    model_down: bool | None = None
    tool_down: list[str] | None = None
    reset: bool = False


class LLMSettingsIn(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class RAGSettingsIn(BaseModel):
    enabled: bool | None = None
    vector_backend: str | None = None          # memory | pgvector
    vector_db_url: str | None = None
    vector_hnsw_ef_search: int | None = None
    embedding_provider: str | None = None      # hash | openai
    embedding_model: str | None = None
    embedding_dim: int | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    topk: int | None = None
    score_threshold: float | None = None
    rerank: bool | None = None


class KBDocIn(BaseModel):
    city: str = "通用"
    title: str = ""
    content: str
    source: str = ""


# ───────── 系统设置 ─────────

@router.get("/settings")
async def get_settings(_: User = Depends(require_admin)):
    llm = await runtime_config.get_llm()
    rag = await runtime_config.get_rag()
    # 出于安全，密钥仅返回是否已配置
    safe_llm = {**llm, "api_key": "", "has_api_key": bool(llm.get("api_key"))}
    safe_rag = {**rag, "embedding_api_key": "",
                "has_embedding_key": bool(rag.get("embedding_api_key"))}
    from ..agent_service.rag.retriever import retriever
    await retriever.ensure_ready()          # 确保索引已构建，返回真实块数
    from ...common.runtime_config import vector_model_ready
    doc_ready, doc_reason = vector_model_ready(rag)
    return ok({"llm": safe_llm, "rag": safe_rag,
               "vector_backend": retriever.backend,
               "kb_chunks": retriever.chunk_count,
               "doc_upload_ready": doc_ready, "doc_upload_reason": doc_reason,
               "kb_documents": await _kb_count()})


@router.put("/settings/llm")
async def update_llm(payload: LLMSettingsIn, _: User = Depends(require_admin)):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "api_key" in data and data["api_key"] == "":
        data.pop("api_key")           # 空串表示不修改
    cfg = await runtime_config.set("llm", data)
    return ok({**cfg, "api_key": "", "has_api_key": bool(cfg.get("api_key"))})


@router.put("/settings/rag")
async def update_rag(payload: RAGSettingsIn, _: User = Depends(require_admin)):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "embedding_api_key" in data and data["embedding_api_key"] == "":
        data.pop("embedding_api_key")        # 空串表示不修改
    cfg = await runtime_config.set("rag", data)
    from ..agent_service.rag.retriever import retriever
    chunks = await retriever.rebuild()      # 参数变更后自动重建索引
    safe = {**cfg, "embedding_api_key": "",
            "has_embedding_key": bool(cfg.get("embedding_api_key"))}
    return ok({**safe, "kb_chunks": chunks, "vector_backend": retriever.backend})


# ───────── 知识库管理 ─────────

async def _kb_count() -> int:
    from ...db.session import SessionLocal
    async with SessionLocal() as db:
        return await db.scalar(select(func.count()).select_from(KBDocument)) or 0


@router.get("/kb")
async def list_kb(city: str | None = None, _: User = Depends(require_admin),
                  db: AsyncSession = Depends(get_session)):
    base = select(KBDocument)
    if city:
        base = base.where(KBDocument.city == city)
    rows = (await db.scalars(base.order_by(KBDocument.id.desc()).limit(200))).all()
    return ok([{"id": r.id, "city": r.city, "title": r.title,
                "content": r.content, "source": r.source,
                "created_at": r.created_at.isoformat() if r.created_at else None}
               for r in rows])


@router.post("/kb")
async def create_kb(payload: KBDocIn, _: User = Depends(require_admin),
                    db: AsyncSession = Depends(get_session)):
    doc = KBDocument(city=payload.city, title=payload.title,
                     content=payload.content, source=payload.source)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    from ..agent_service.rag.retriever import retriever
    await retriever.rebuild()
    return ok({"id": doc.id, "city": doc.city, "title": doc.title})


@router.delete("/kb/{doc_id}")
async def delete_kb(doc_id: int, _: User = Depends(require_admin),
                    db: AsyncSession = Depends(get_session)):
    doc = await db.get(KBDocument, doc_id)
    if doc is None:
        raise NotFoundError("知识库文档不存在")
    await db.delete(doc)
    await db.commit()
    from ..agent_service.rag.retriever import retriever
    await retriever.rebuild()
    return ok({"deleted": doc_id})


@router.post("/kb/reindex")
async def reindex_kb(_: User = Depends(require_admin)):
    from ..agent_service.rag.retriever import retriever
    chunks = await retriever.rebuild()
    return ok({"chunks": chunks})


@router.post("/kb/search")
async def search_kb(query: str = Query(...), city: str = "",
                    _: User = Depends(require_admin)):
    """检索测试：验证 RAG 真实可用。"""
    from ..agent_service.rag.retriever import retriever
    hits = await retriever.retrieve(query, city=city or None)
    return ok({"query": query, "hits": hits, "chunks": retriever.chunk_count})


_SELFTEST_FILE = "rag_selftest.txt"


@router.post("/kb/selftest")
async def kb_selftest(probe: str = Query("成都 熊猫基地 门票 开放时间"),
                      _: User = Depends(require_admin),
                      db: AsyncSession = Depends(get_session)):
    """RAG 全链路自检：用内置测试 txt 走完 清洗 → 切片 → 向量化 → 入库 → 检索。

    逐步返回每一环的真实结果与「有效/无效」判定，便于确认：
    原料清洗是否有效、原切片/embedding/检索机制是否仍在、pgvector 是否可用。
    """
    from pathlib import Path as _Path

    from ...common.runtime_config import runtime_config, vector_model_ready
    from ..agent_service.rag.chunker import chunk_documents
    from ..agent_service.rag.retriever import retriever
    from ..media_service.parsers import parse_document

    path = _Path(__file__).resolve().parents[3] / "data" / _SELFTEST_FILE
    if not path.exists():
        raise NotFoundError(f"自检样本不存在：{_SELFTEST_FILE}")

    cfg = await runtime_config.get_rag()
    ready, reason = vector_model_ready(cfg)

    # ① 原料清洗
    parsed = parse_document(_SELFTEST_FILE, path.read_bytes(), "text/plain")
    clean = parsed.get("clean", {}) if parsed.get("ok") else {}

    # ② 切片（同级切片参数，独立统计本样本产出块数）
    doc = {"city": "通用", "title": "RAG链路自检样本",
           "content": parsed.get("text", ""), "source": f"selftest:{_SELFTEST_FILE}"}
    chunks = chunk_documents([doc], chunk_size=int(cfg.get("chunk_size", 380)),
                             overlap=int(cfg.get("chunk_overlap", 50))) \
        if parsed.get("ok") else []

    # ③ 入库：先删同源旧样本（幂等），再写库并重建索引
    from sqlalchemy import delete
    await db.execute(delete(KBDocument).where(KBDocument.source == doc["source"]))
    await db.commit()
    if parsed.get("ok"):
        db.add(KBDocument(city=doc["city"], title=doc["title"],
                          content=doc["content"], source=doc["source"]))
        await db.commit()
    total_chunks = await retriever.rebuild()
    store_size = await retriever.store.size()

    # ④ 检索
    hits = await retriever.retrieve(probe, topk=int(cfg.get("topk", 5)))
    hit_in_sample = any((doc["title"] in (h.get("title") or "")
                         or "熊猫" in (h.get("text") or "")) for h in hits)

    stages = [
        {"name": "原料清洗", "ok": bool(parsed.get("ok")) and clean.get("clean_chars", 0) > 0,
         "detail": clean},
        {"name": "两级切片", "ok": len(chunks) > 0,
         "detail": {"chunks": len(chunks),
                    "chunk_size": cfg.get("chunk_size"), "overlap": cfg.get("chunk_overlap")}},
        {"name": "向量化", "ok": ready,
         "detail": {"provider": cfg.get("embedding_provider"),
                    "model": cfg.get("embedding_model"), "dim": cfg.get("embedding_dim"),
                    "note": "" if ready else reason}},
        {"name": "向量库入库", "ok": store_size >= len(chunks) and store_size > 0,
         "detail": {"backend": retriever.backend, "store_size": store_size,
                    "indexed_chunks": total_chunks}},
        {"name": "检索召回", "ok": len(hits) > 0 and hit_in_sample,
         "detail": {"query": probe, "hits": len(hits),
                    "score_threshold": cfg.get("score_threshold"),
                    "top": [{"title": h.get("title"), "score": h.get("score"),
                             "text": (h.get("text") or "")[:80]} for h in hits[:3]]}},
    ]
    return ok({
        "passed": all(s["ok"] for s in stages),
        "probe": probe, "vector_backend": retriever.backend,
        "embedding_provider": cfg.get("embedding_provider"),
        "total_chunks": total_chunks, "stages": stages,
        "sample": {"file": _SELFTEST_FILE, "chars": len(parsed.get("text", "")),
                   "preview": parsed.get("text", "")[:160]},
    })


# ───────── 统计 ─────────

@router.get("/stats")
async def stats(_: User = Depends(require_admin), db: AsyncSession = Depends(get_session)):
    users = await db.scalar(select(func.count()).select_from(User)) or 0
    posts = await db.scalar(select(func.count()).select_from(Post)) or 0
    trips = await db.scalar(select(func.count()).select_from(Trip)) or 0
    kb = await _kb_count()
    return ok({"users": users, "posts": posts, "trips": trips, "kb_documents": kb})


# ───────── 可观测性 ─────────

@router.get("/overview")
async def overview(_: User = Depends(require_admin)):
    from ..agent_service.sse.manager import manager
    snap = metrics.snapshot()
    return ok({
        "counters": snap["counters"], "gauges": snap["gauges"], "p95_ms": snap["p95"],
        "tokens_last_hour": snap["tokens_last_hour"],
        "sse_connections": manager.online_count(), "breakers": all_breakers(),
    })


# ─────────────────────────── 黑名单 ───────────────────────────

class BlacklistIn(BaseModel):
    user_id: int
    reason: str = ""


def _user_brief(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "nickname": u.nickname or u.username,
        "avatar": u.avatar or "", "role": u.role or "user",
        "banned": bool(u.banned), "ban_reason": u.ban_reason or "",
        "banned_at": u.banned_at.isoformat(sep=" ", timespec="minutes") if u.banned_at else None,
    }


@router.get("/users")
async def list_users(keyword: str = "", banned: int | None = None,
                     limit: int = Query(30, ge=1, le=200),
                     _: User = Depends(require_admin),
                     db: AsyncSession = Depends(get_session)):
    """用户检索：供管理员选择拉黑对象；banned=1 只看黑名单。"""
    from sqlalchemy import or_
    stmt = select(User)
    if keyword.strip():
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(User.username.like(kw), User.nickname.like(kw)))
    if banned is not None:
        stmt = stmt.where(User.banned == banned)
    rows = (await db.scalars(
        stmt.order_by(User.banned.desc(), User.id.asc()).limit(limit))).all()
    return ok([_user_brief(u) for u in rows])


@router.get("/blacklist")
async def list_blacklist(_: User = Depends(require_admin),
                         db: AsyncSession = Depends(get_session)):
    """黑名单列表（被拉黑的用户）。"""
    rows = (await db.scalars(
        select(User).where(User.banned == 1).order_by(User.banned_at.desc()))).all()
    return ok([_user_brief(u) for u in rows])


@router.post("/blacklist")
async def add_blacklist(payload: BlacklistIn, admin: User = Depends(require_admin),
                        db: AsyncSession = Depends(get_session)):
    """拉黑用户：之后该用户无法发布动态、点赞、评论、收藏等社区互动。"""
    from ...common.errors import ValidationError
    target = await db.get(User, payload.user_id)
    if target is None:
        raise NotFoundError("用户不存在")
    if target.id == admin.id:
        raise ValidationError("不能拉黑自己")
    if (target.role or "user") == "admin":
        raise ValidationError("不能拉黑管理员账号")
    target.banned = 1
    target.ban_reason = (payload.reason or "").strip()[:120]
    target.banned_at = datetime.utcnow()
    # 站内通知当事人
    from ...common.notify import notify
    await notify(db, user_id=target.id, kind="system", title="你已被加入黑名单",
                 content=(f"原因：{target.ban_reason}" if target.ban_reason
                          else "如有疑问请联系管理员。"),
                 link="/moments")
    await db.commit()
    await db.refresh(target)
    return ok(_user_brief(target))


@router.delete("/blacklist/{user_id}")
async def remove_blacklist(user_id: int, _: User = Depends(require_admin),
                           db: AsyncSession = Depends(get_session)):
    """移出黑名单（恢复发言与互动权限）。"""
    target = await db.get(User, user_id)
    if target is None:
        raise NotFoundError("用户不存在")
    target.banned = 0
    target.ban_reason = ""
    target.banned_at = None
    from ...common.notify import notify
    await notify(db, user_id=target.id, kind="system", title="你已被移出黑名单",
                 content="已恢复发布动态与互动权限。", link="/moments")
    await db.commit()
    await db.refresh(target)
    return ok(_user_brief(target))


@router.get("/breakers")
async def breakers(_: User = Depends(require_admin)):
    return ok(all_breakers())


@router.get("/traces")
async def traces(trace_id: str | None = None, limit: int = 30,
                 _: User = Depends(require_admin)):
    if trace_id:
        return ok({"trace_id": trace_id, "spans": tracer.recent(trace_id, 200)})
    return ok(tracer.traces(limit))


@router.get("/sse")
async def sse_connections(_: User = Depends(require_admin)):
    from ..agent_service.sse.manager import manager
    return ok(manager.snapshot())


@router.get("/fault")
async def get_fault(_: User = Depends(require_admin)):
    return ok(fault.snapshot())


@router.post("/fault")
async def set_fault(payload: FaultIn, _: User = Depends(require_admin)):
    if payload.reset:
        fault.reset()
    if payload.model_down is not None:
        fault.model_down = payload.model_down
    if payload.tool_down is not None:
        fault.tool_down = set(payload.tool_down)
    return ok(fault.snapshot())


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    # 供 Prometheus 抓取，不做鉴权
    return metrics.to_prometheus()
