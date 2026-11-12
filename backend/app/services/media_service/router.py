"""media-service：图片资源保存到后端图片文件夹。

设计：图片二进制文件落盘在后端 `static/uploads/` 目录（按内容哈希分桶去重），
数据库 `media` 表只存元数据与相对路径——文件本体在文件系统、登记信息在 MySQL，
两头都可持久化，且不依赖外部图床。对外仍由 `GET /api/media/{id}` 统一提供，
前端地址不变。支持把历史外链图片「同步落盘」。
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.errors import NotFoundError, ValidationError
from ...common.config import settings
from ...common.logging import get_logger
from ...common.runtime_config import runtime_config, vector_model_ready
from ...db.models import KBDocument, Media, Post, User
from ...db.session import get_session
from ...gateway.deps import get_current_user
from ...schemas.common import ok
from .parsers import SUPPORTED_HINT, parse_document

router = APIRouter(prefix="/api/media", tags=["media-service"])
admin_router = APIRouter(prefix="/api/admin/media", tags=["media-service"])
logger_doc = get_logger("media")

MAX_BYTES = 5 * 1024 * 1024          # 单文件 5MB
MAX_DOC_BYTES = settings.doc_upload_max_bytes   # 知识文档上限（默认 10MB）
ALLOWED_MIME = {"image/jpeg": ".jpg", "image/png": ".png",
                "image/webp": ".webp", "image/gif": ".gif",
                "image/svg+xml": ".svg"}          # 内置生成的矢量头像
EXT_MIME = {ext: mime for mime, ext in ALLOWED_MIME.items()}

# 后端图片文件夹：backend/static/uploads
UPLOAD_DIR = Path(__file__).resolve().parents[3] / "static" / "uploads"


async def store_bytes(db: AsyncSession, data: bytes, *, mime: str, owner_id: int | None = None,
                      kind: str = "image", filename: str = "",
                      source_url: str = "") -> Media:
    """图片落盘（按 sha256 去重），元数据登记进数据库。"""
    digest = hashlib.sha256(data).hexdigest()
    existing = await db.scalar(select(Media).where(Media.sha256 == digest))
    if existing is not None:
        return existing

    ext = ALLOWED_MIME.get(mime, ".jpg")
    rel_path = f"{kind}/{digest[:2]}/{digest}{ext}"
    abs_path = UPLOAD_DIR / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    if not abs_path.exists():
        abs_path.write_bytes(data)

    row = Media(owner_id=owner_id, kind=kind, filename=filename[:160], mime=mime,
                size=len(data), sha256=digest, path=rel_path, source_url=source_url[:512])
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def media_url(media_id: int) -> str:
    return f"/api/media/{media_id}"


# ─────────────── 图片引用统一落盘（data: URL / 外链 → 后端资源文件夹） ───────────────

_DATA_URL = re.compile(r"^data:(?P<mime>[^;,]*)(?P<params>[^,]*),(?P<data>.*)$", re.S)
_LOCAL_PATH = re.compile(r"^(?:[a-zA-Z]:[\\/]|\\\\|file:|blob:|/Users/|/home/)")


def _sniff_mime(raw: bytes, fallback: str = "") -> str:
    """按文件头猜图片类型；猜不出时用调用方给的 MIME 兜底。"""
    if raw.startswith(b"\x89PNG"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"GIF8"):
        return "image/gif"
    if raw.lstrip()[:5].lower() in (b"<svg ", b"<?xml") and b"<svg" in raw[:400]:
        return "image/svg+xml"
    return fallback if fallback in ALLOWED_MIME else ""


def _decode_data_url(value: str) -> tuple[bytes, str] | None:
    m = _DATA_URL.match(value)
    if not m:
        return None
    raw = (m.group("data") or "").strip()
    params = (m.group("params") or "").lower()
    try:
        if "base64" in params:
            data = base64.b64decode(raw, validate=False)
        else:
            from urllib.parse import unquote_to_bytes
            data = unquote_to_bytes(raw)
    except Exception:
        return None
    mime = _sniff_mime(data, (m.group("mime") or "").strip().lower())
    return (data, mime) if mime and data else None


async def materialize_image(db: AsyncSession, value: str, *, owner_id: int | None = None,
                            kind: str = "image") -> Media | None:
    """把单个「图片引用」落到后端资源文件夹，返回 Media 记录。

    支持三类输入：后端路径（/api/media/x，视为已落盘）、data: URL、http(s) 外链。
    返回 None 表示无法落盘（本地磁盘路径 / 不可下载的外链），调用方据此忽略，
    避免把「路径文字」当作图片存进数据库。
    """
    val = (value or "").strip()
    if not val:
        return None
    if val.startswith("/api/media/"):
        return None                                  # 已是后端路径，无需处理
    got: tuple[bytes, str] | None = None
    if val.startswith("data:"):
        got = _decode_data_url(val)
    elif val.startswith(("http://", "https://")):
        got = await _download(val)
    elif _LOCAL_PATH.match(val):
        logger_doc.warning("忽略本地磁盘路径（图片未真正上传）: %s", val[:80])
        return None
    if got is None:
        return None
    data, mime = got
    if not mime or mime not in ALLOWED_MIME or len(data) > MAX_BYTES:
        return None
    return await store_bytes(db, data, mime=mime, owner_id=owner_id, kind=kind,
                             source_url=val[:512])


async def materialize_or_keep(db: AsyncSession, value: str, *, owner_id: int | None = None,
                              kind: str = "image") -> tuple[str, str]:
    """把单个图片引用「尽量落盘」，返回 (最终引用, 错误信息)。

    规则（既解决「只存路径文字」的 bug，又不破坏可用的外链）：
    - 已经是 /api/media/x → 原样返回；
    - 本地磁盘路径 / file: / blob: → 返回错误（这类值浏览器根本加载不出来）；
    - http(s) 外链 → 下载后落盘；下载失败保留原外链（保证仍能显示）；
    - data: URL → 解码后落盘；解析失败返回错误。
    """
    val = (value or "").strip()
    if not val:
        return "", ""
    if val.startswith("/api/media/"):
        return val, ""
    if _LOCAL_PATH.match(val):
        return "", ("检测到本地磁盘路径，图片并未真正上传："
                    "请用「上传图片」按钮选择本地文件，图片会保存到后端资源文件夹")
    row = await materialize_image(db, val, owner_id=owner_id, kind=kind)
    if row is not None:
        return media_url(row.id), ""
    if val.startswith(("http://", "https://")):
        return val, ""                     # 外链下载失败：保留原地址，不阻断保存
    return "", "图片内容无法解析，请改用「上传图片」按钮选择本地文件"


async def materialize_images(db: AsyncSession, values: list[str], *,
                             owner_id: int | None = None, kind: str = "image") -> list[str]:
    """批量处理并返回可用引用列表（本地磁盘路径这类无效值直接丢弃）。"""
    out: list[str] = []
    for v in values or []:
        url, err = await materialize_or_keep(db, v, owner_id=owner_id, kind=kind)
        if url:
            out.append(url)
        elif err:
            logger_doc.warning("配图被丢弃：%s（%s）", (v or "")[:60], err)
    return out


@router.get("/{media_id}")
async def get_media(media_id: int, db: AsyncSession = Depends(get_session)):
    row = await db.get(Media, media_id)
    if row is None:
        raise NotFoundError("图片不存在")
    abs_path = UPLOAD_DIR / row.path
    if not abs_path.exists():
        raise NotFoundError("图片文件缺失")
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    if (row.mime or "").startswith("image/svg"):
        # SVG 可能内嵌脚本：以 CSP 禁止脚本执行，避免直接访问该地址时被利用
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
        headers["X-Content-Type-Options"] = "nosniff"
    return FileResponse(str(abs_path), media_type=row.mime or "image/jpeg", headers=headers)


@router.post("/upload")
async def upload(file: UploadFile = File(...),
                 kind: str = Query("image", pattern="^(image|avatar)$"),
                 user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_session)):
    raw = await file.read()
    if not raw:
        raise ValidationError("文件为空")
    if len(raw) > MAX_BYTES:
        raise ValidationError("图片过大（上限 5MB）")
    mime = (file.content_type or "image/jpeg").split(";")[0].strip()
    if mime not in ALLOWED_MIME:
        raise ValidationError(f"不支持的图片格式：{mime}")
    row = await store_bytes(db, raw, mime=mime, owner_id=user.id, kind=kind,
                            filename=file.filename or "")
    return ok({"id": row.id, "url": media_url(row.id), "size": row.size, "mime": row.mime})


@router.get("/mine/list")
async def my_media(user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_session)):
    rows = (await db.scalars(
        select(Media).where(Media.owner_id == user.id)
        .order_by(Media.created_at.desc()).limit(100))).all()
    return ok([{"id": r.id, "url": media_url(r.id), "kind": r.kind, "size": r.size,
                "created_at": r.created_at.isoformat() if r.created_at else None}
               for r in rows])


# ─────────────── 知识文档上传（pdf / wps(docx) / txt / md → RAG） ───────────────

# MCP 走 stdio 传 base64，超大文件不做搬运，直接本地解析
_MCP_PARSE_MAX = 4 * 1024 * 1024


async def parse_via_mcp_or_local(filename: str, raw: bytes, mime: str = "") -> dict:
    """统一解析入口：优先交给 mcp-server（解析能力统一托管），失败回落本地。

    这样「文档解析」这一能力与其它工具一样由 MCP 统一管理；
    MCP 未就绪或文件过大时使用进程内实现，保证上传链路始终可用。
    """
    if len(raw) <= _MCP_PARSE_MAX:
        try:
            import base64

            from ..mcp_service.manager import McpUnavailable, mcp_manager
            if mcp_manager.enabled:
                res = await mcp_manager.call_tool("parse_document", {
                    "file_name": filename or "upload.txt",
                    "content_base64": base64.b64encode(raw).decode("ascii"),
                })
                if isinstance(res, dict) and "ok" in res:
                    return res
        except McpUnavailable:
            pass
        except Exception as exc:
            logger_doc.warning("MCP 文档解析失败，回落本地解析: %s", exc)
    return parse_document(filename, raw, mime)


@router.post("/upload_doc")
async def upload_document(
    file: UploadFile = File(...),
    city: str = Query("通用"),
    title: str = Query(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """上传知识文档 → 解析清洗 → 写入知识库 → 重建向量索引。

    前置条件：管理员已配置向量模型，否则返回「该功能暂未开放」。
    """
    cfg = await runtime_config.get_rag()
    ready, reason = vector_model_ready(cfg)
    if not ready:
        raise ValidationError(reason)

    raw = await file.read()
    if not raw:
        raise ValidationError("文件为空")
    if len(raw) > MAX_DOC_BYTES:
        raise ValidationError(f"文档过大（上限 {MAX_DOC_BYTES // 1024 // 1024}MB）")

    parsed = await parse_via_mcp_or_local(file.filename or "", raw, file.content_type or "")
    if not parsed.get("ok"):
        raise ValidationError(parsed.get("error") or f"文档解析失败，{SUPPORTED_HINT}")

    doc_title = (title or Path(file.filename or "").stem or "上传文档")[:200]
    doc_source = f"upload:{file.filename or ''}"[:200]
    # 同名文件重复上传按「覆盖」处理：先删旧记录，避免知识库出现重复片段
    from sqlalchemy import delete
    await db.execute(delete(KBDocument).where(KBDocument.source == doc_source))
    doc = KBDocument(city=city or "通用", title=doc_title,
                     content=parsed["text"], source=doc_source)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # 重建索引：把新文档切片 → 向量化 → 入库（pgvector/内存后端由配置决定）
    from ..agent_service.rag.chunker import chunk_documents
    from ..agent_service.rag.retriever import retriever

    own_chunks = len(chunk_documents(
        [{"city": doc.city, "title": doc.title, "content": doc.content,
          "source": doc.source}],
        chunk_size=int(cfg.get("chunk_size", 380)),
        overlap=int(cfg.get("chunk_overlap", 50))))
    total_chunks = await retriever.rebuild()
    return ok({
        "document_id": doc.id, "title": doc.title, "city": doc.city,
        "file_type": parsed["kind"], "meta": parsed["meta"], "clean": parsed["clean"],
        "chunks": own_chunks, "total_chunks": total_chunks,
        "vector_backend": retriever.backend,
        "embedding_provider": cfg.get("embedding_provider"),
        "preview": doc.content[:180],
    })


@router.get("/doc/list")
async def list_my_docs(city: str | None = None,
                       user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_session)):
    """查看当前知识库中的文档（供上传后核对入库结果）。"""
    base = select(KBDocument).where(KBDocument.source.like("upload:%"))
    if city:
        base = base.where(KBDocument.city == city)
    rows = (await db.scalars(base.order_by(KBDocument.id.desc()).limit(50))).all()
    return ok([{"id": r.id, "city": r.city, "title": r.title,
                "source": r.source, "chars": len(r.content or ""),
                "created_at": r.created_at.isoformat() if r.created_at else None}
               for r in rows])


# ─────────────── 把外链图片同步落盘（管理员） ───────────────

async def _download(url: str) -> tuple[bytes, str] | None:
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "TravelAgent/1.0"})
            if resp.status_code != 200:
                return None
            mime = (resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
            if mime not in ALLOWED_MIME:
                mime = "image/jpeg"
            data = resp.content
            if not data or len(data) > MAX_BYTES * 2:
                return None
            return data, mime
    except Exception:
        return None


async def sync_images(limit: int = 60) -> dict:
    """把帖子配图与用户头像中的外链地址下载落盘，数据库登记并替换为本地地址。

    供管理员手动触发，也用于首次启动时的自动迁移。
    """
    import json as _json

    from ...db.session import SessionLocal

    stats = {"posts_scanned": 0, "images_stored": 0, "avatars_stored": 0, "failed": 0}
    budget = limit

    async with SessionLocal() as db:
        # 1) 帖子配图
        posts = (await db.scalars(select(Post).order_by(Post.id.desc()))).all()
        for post in posts:
            if budget <= 0:
                break
            stats["posts_scanned"] += 1
            try:
                urls = _json.loads(post.images or "[]")
            except Exception:
                continue
            if not isinstance(urls, list):
                continue
            changed = False
            new_urls: list[str] = []
            for url in urls:
                if not isinstance(url, str) or url.startswith("/api/media/"):
                    new_urls.append(url)
                    continue
                if budget <= 0:
                    new_urls.append(url)
                    continue
                got = await _download(url)
                budget -= 1
                if got is None:
                    stats["failed"] += 1
                    new_urls.append(url)     # 下载失败保留原地址，不影响业务
                    continue
                data, mime = got
                row = await store_bytes(db, data, mime=mime, owner_id=post.user_id,
                                        kind="image", source_url=url)
                new_urls.append(media_url(row.id))
                stats["images_stored"] += 1
                changed = True
            if changed:
                post.images = _json.dumps(new_urls, ensure_ascii=False)
                await db.commit()

        # 2) 用户头像
        for u in (await db.scalars(select(User))).all():
            if budget <= 0:
                break
            url = (u.avatar or "").strip()
            if not url or url.startswith("/api/media/") or url.startswith("data:"):
                continue
            got = await _download(url)
            budget -= 1
            if got is None:
                stats["failed"] += 1
                continue
            data, mime = got
            row = await store_bytes(db, data, mime=mime, owner_id=u.id, kind="avatar",
                                    source_url=url)
            u.avatar = media_url(row.id)
            await db.commit()
            stats["avatars_stored"] += 1

        total = await db.scalar(select(func.count()).select_from(Media)) or 0
        return {**stats, "media_total": total}


async def auto_migrate_once() -> None:
    """首次启动时把外链图片迁移落盘（媒体表为空时才执行，失败静默）。"""
    from ...db.session import SessionLocal
    try:
        async with SessionLocal() as db:
            count = await db.scalar(select(func.count()).select_from(Media)) or 0
        if count:
            return
        result = await sync_images(limit=80)
        if result["images_stored"] or result["avatars_stored"]:
            import logging
            logging.getLogger("travelagent.media").info(
                "外链图片已迁移落盘: %s", result)
    except Exception:
        pass


@admin_router.post("/sync")
async def sync_external_images(limit: int = Query(60, ge=1, le=400),
                               user: User = Depends(get_current_user)):
    if (user.role or "user") != "admin":
        from ...common.errors import ForbiddenError
        raise ForbiddenError("需要管理员权限")
    return ok(await sync_images(limit=limit))


@admin_router.get("/stats")
async def media_stats(user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_session)):
    if (user.role or "user") != "admin":
        from ...common.errors import ForbiddenError
        raise ForbiddenError("需要管理员权限")
    total = await db.scalar(select(func.count()).select_from(Media)) or 0
    total_bytes = await db.scalar(select(func.coalesce(func.sum(Media.size), 0))) or 0
    files_on_disk = sum(1 for _ in UPLOAD_DIR.rglob("*") if _.is_file()) if UPLOAD_DIR.exists() else 0
    return ok({"count": total, "bytes": int(total_bytes),
               "mb": round(int(total_bytes) / 1024 / 1024, 2),
               "files_on_disk": files_on_disk,
               "dir": str(UPLOAD_DIR)})
