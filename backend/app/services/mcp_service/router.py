"""mcp-service 路由：MCP 运行状态、工具清单与调试调用。

- 状态：前端/管理端可观察 MCP 是否就绪、健康检查与重连次数；
- 工具清单：列出 mcp-server 经 MCP 协议暴露的全部工具（含 JSON Schema）；
- 调试调用：管理员可手工调用某个 MCP 工具，验证协议链路真实可用。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...db.models import User
from ...common.errors import ValidationError
from ...gateway.deps import get_current_user, require_admin
from ...schemas.common import ok
from .manager import McpUnavailable, mcp_manager

router = APIRouter(prefix="/api/mcp", tags=["mcp-service"])


class McpCallIn(BaseModel):
    tool: str
    arguments: dict = {}


@router.get("/status")
async def status(_: User = Depends(get_current_user)):
    snap = mcp_manager.snapshot()
    return ok({k: v for k, v in snap.items() if k != "tools"})


@router.get("/tools")
async def tools(_: User = Depends(require_admin)):
    snap = mcp_manager.snapshot()
    return ok({"status": snap["status"], "error": snap["error"],
               "tools": mcp_manager.tools_view()})


@router.post("/call")
async def call(payload: McpCallIn, _: User = Depends(require_admin)):
    if not mcp_manager.enabled:
        raise ValidationError("MCP 未就绪，请检查服务端配置与日志")
    try:
        result = await mcp_manager.call_tool(payload.tool, payload.arguments)
    except McpUnavailable as exc:
        raise ValidationError(f"MCP 调用失败：{exc}")
    return ok({"tool": payload.tool, "result": result})
