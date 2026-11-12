"""统一错误码与业务异常。

错误码为五位数字：前三位对应 HTTP 语义，后两位为业务子码。
例如 42901 限流、50301 模型降级中。
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """业务异常基类。"""

    http_status: int = 400
    code: int = 40000
    message: str = "请求错误"

    def __init__(self, message: str | None = None, *, code: int | None = None,
                 http_status: int | None = None, data: Any = None) -> None:
        self.message = message or self.message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        self.data = data
        super().__init__(self.message)


class ValidationError(AppError):
    http_status, code, message = 400, 40001, "参数校验失败"


class UnauthorizedError(AppError):
    http_status, code, message = 401, 40101, "未登录或登录已过期"


class ForbiddenError(AppError):
    http_status, code, message = 403, 40301, "无权访问该资源"


class NotFoundError(AppError):
    http_status, code, message = 404, 40401, "资源不存在"


class ConflictError(AppError):
    http_status, code, message = 409, 40901, "资源冲突"


class RateLimitError(AppError):
    http_status, code, message = 429, 42901, "请求过于频繁，请稍后重试"

    def __init__(self, retry_after: int = 60, message: str | None = None) -> None:
        super().__init__(message or f"请求过于频繁，请 {retry_after} 秒后重试")
        self.retry_after = retry_after


class TokenQuotaError(AppError):
    http_status, code, message = 429, 42902, "今日 Token 配额已用尽，请次日再试"


class ModelDegradedError(AppError):
    http_status, code, message = 503, 50301, "智能规划服务暂时不可用（已降级）"


class UpstreamError(AppError):
    http_status, code, message = 502, 50201, "上游依赖调用失败"
