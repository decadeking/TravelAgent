"""网关中间件：trace_id 注入 + 统一异常响应 + 访问日志 + 指标。"""
from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..common import context
from ..common.errors import AppError
from ..common.logging import get_logger
from ..common.metrics import metrics

logger = get_logger("gateway")


class TraceMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 trace_id 与 request_id，并在响应头返回 X-Trace-Id。"""

    async def dispatch(self, request: Request, call_next):
        # trace_id 优先取 X-Trace-Id，其次解析 W3C traceparent（Q43 链路传播）
        trace_id = (request.headers.get("X-Trace-Id")
                    or context.parse_traceparent(request.headers.get("traceparent"))
                    or context.new_trace_id())
        request_id = request.headers.get("X-Request-Id", "")
        context.set_trace_id(trace_id)
        request.state.trace_id = trace_id
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except AppError:
            raise
        latency_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Trace-Id"] = trace_id
        response.headers["traceparent"] = context.make_traceparent(trace_id)
        metrics.inc("http_requests_total")
        metrics.observe("http_latency", latency_ms)
        logger.info("access", extra={"latency_ms": round(latency_ms, 2)})
        return response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        headers = {}
        if hasattr(exc, "retry_after"):
            headers["Retry-After"] = str(getattr(exc, "retry_after"))
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "data": exc.data},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={"code": 40001, "message": "参数校验失败",
                     "data": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.error("未处理异常", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"code": 50001, "message": "服务器内部错误", "data": None},
        )
