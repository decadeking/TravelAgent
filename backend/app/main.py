"""应用入口：装配网关中间件 + 各微服务路由。

「逻辑微服务、轻量部署」：代码按服务边界彻底分目录，
由本入口统一装配成一个可运行的 FastAPI 应用；
生产形态下每个服务可独立容器部署（见 deploy/）。
"""
from __future__ import annotations

import asyncio
import os

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .common.config import settings
from .common.kvstore import close_kv
from .common.logging import get_logger
from .db.seed import seed
from .db.session import SessionLocal, init_db
from .gateway.middleware import TraceMiddleware, register_exception_handlers
from .services.admin_service.router import router as admin_router
from .services.agent_service.router import router as agent_router
from .services.feed_service.router import admin_router as feed_admin_router
from .services.feed_service.router import router as feed_router
from .services.knowledge_service.router import router as knowledge_router
from .services.media_service.router import admin_router as media_admin_router
from .services.media_service.router import router as media_router
from .services.mcp_service.router import router as mcp_router
from .services.message_service.router import router as message_router
from .services.tool_service.router import router as tool_router
from .services.trip_service.router import router as trip_router
from .services.user_service.router import router as user_router

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as db:
        await seed(db)
    # 首次启动：把历史外链图片迁移落盘（后台执行，不阻塞启动）
    migrate_task = None
    if os.environ.get("AUTO_MIGRATE", "1") != "0":
        from .services.media_service.router import auto_migrate_once
        migrate_task = asyncio.create_task(auto_migrate_once())
    # 行程提醒调度器：定期把到期提醒转成站内通知
    reminder_task = None
    if os.environ.get("REMINDER_LOOP", "1") != "0":
        from .services.agent_service.reminders import reminder_loop
        reminder_task = asyncio.create_task(reminder_loop())
    # MCP：以子进程方式拉起 mcp-server，为智能体提供统一工具（失败自动旁路原生工具）
    from .services.mcp_service.manager import mcp_manager
    await mcp_manager.start()
    logger.info("服务启动完成", extra={"event": "startup"})
    yield
    if migrate_task is not None:
        migrate_task.cancel()
    if reminder_task is not None:
        reminder_task.cancel()
    await mcp_manager.stop()
    await close_kv()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于 FastAPI + LangGraph 风格状态图的交互式旅行规划智能体",
    lifespan=lifespan,
)

# 网关中间件与异常处理
app.add_middleware(TraceMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)
register_exception_handlers(app)

# 各微服务路由装配
app.include_router(user_router)
app.include_router(trip_router)
app.include_router(tool_router)
app.include_router(agent_router)
app.include_router(feed_router)
app.include_router(feed_admin_router)
app.include_router(media_router)
app.include_router(media_admin_router)
app.include_router(message_router)
app.include_router(knowledge_router)
app.include_router(mcp_router)
app.include_router(admin_router)


@app.get("/api/health")
async def health():
    return {"code": 0, "message": "ok",
            "data": {"service": "travel-agent", "version": settings.app_version,
                     "llm_provider": settings.llm_provider,
                     "kv_backend": settings.kv_backend}}


# 生产形态：托管前端构建产物（存在 frontend/dist 时生效）
# 说明：不能直接 mount("/")——那样 /login 这类前端路由会 404。
# 改为挂载 assets 目录 + 通配路由回退到 index.html（SPA history 模式）。
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    from fastapi.responses import FileResponse

    _ASSETS = _DIST / "assets"
    if _ASSETS.exists():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        if full_path.startswith("api"):
            return JSONResponse(status_code=404,
                                content={"code": 40401, "message": "接口不存在", "data": None})
        candidate = (_DIST / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(_DIST)):
            return FileResponse(str(candidate))
        return FileResponse(str(_DIST / "index.html"))


@app.exception_handler(404)
async def _not_found(request, exc):
    return JSONResponse(status_code=404,
                        content={"code": 40401, "message": "接口不存在", "data": None})
