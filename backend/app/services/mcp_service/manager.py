"""MCP 客户端管理器：把 mcp-server 作为子进程拉起，维持长连接并做健康检查。

设计要点
- **连接拥有者任务**：stdio 客户端与 ClientSession 都是「异步上下文管理器」，
  必须在同一个任务里进入与退出，否则会出现 cancel scope 跨任务的经典报错。
  这里用一个常驻后台任务专门持有连接，其它协程只通过 session 发请求。
- **健康检查用真实请求**：只判断「连接标识」无法发现静默断开的「假连接」，
  因此定期 list_tools() 探活；失败或工具调用异常即触发重连（指数退避）。
- **优雅降级**：未启用 / SDK 缺失 / 子进程启动失败时状态置为 error，
  上层自动旁路到原生工具实现，业务不中断。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from ...common.config import settings
from ...common.logging import get_logger

logger = get_logger("mcp.manager")

_BACKEND_DIR = Path(__file__).resolve().parents[3]

# 智能体侧工具名 → MCP 工具名（个别名称对齐，其余同名）
TOOL_ALIAS = {"set_reminder": "set_alarm"}


class McpUnavailable(RuntimeError):
    """MCP 不可用（未启用 / 未就绪 / 传输失败）时抛出，由上层回落原生实现。"""


def _extract_result(res: Any) -> dict:
    """把 MCP 的 CallToolResult 归一化为普通 dict。"""
    if getattr(res, "isError", False):
        texts = "\n".join(getattr(c, "text", "") for c in (res.content or []))
        return {"error": texts.strip() or "MCP 工具执行失败"}
    sc = getattr(res, "structuredContent", None)
    if isinstance(sc, dict):
        # FastMCP 对非对象返回值会包一层 {"result": value}
        if set(sc.keys()) == {"result"} and isinstance(sc["result"], (dict, list)):
            return sc["result"] if isinstance(sc["result"], dict) else {"items": sc["result"]}
        return sc
    texts = [getattr(c, "text", "") for c in (res.content or [])]
    raw = "\n".join(t for t in texts if t).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {"text": raw}
    if isinstance(parsed, dict) and set(parsed.keys()) == {"result"} \
            and isinstance(parsed["result"], dict):
        return parsed["result"]
    return parsed if isinstance(parsed, dict) else {"items": parsed}


def _to_openai_schema(tool: Any) -> dict:
    """MCP 工具定义 → OpenAI Function Calling schema。"""
    params = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
    return {"type": "function", "function": {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", "") or "",
        "parameters": params,
    }}


class McpManager:
    def __init__(self) -> None:
        self.session: Any = None
        self.status = "disabled"          # disabled | starting | ready | error
        self.error = ""
        self.server_name = ""
        self.started_at: str = ""
        self._tools: list[dict] = []
        self._tool_names: set[str] = set()
        self._owner: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._stop_evt: asyncio.Event | None = None
        self._reload_evt: asyncio.Event | None = None
        self._ready_evt: asyncio.Event | None = None
        # 可观测计数（供管理端查看 MCP 运行情况）
        self.checks = 0
        self.reloads = 0
        self.calls = 0
        self.failures = 0

    # ───────────── 生命周期 ─────────────

    @property
    def enabled(self) -> bool:
        return self.status == "ready" and self.session is not None

    @property
    def tool_names(self) -> set[str]:
        return set(self._tool_names)

    def _params(self):
        from mcp import StdioServerParameters
        py = settings.mcp_python or sys.executable
        cwd = settings.mcp_server_cwd or str(_BACKEND_DIR)
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")
        return StdioServerParameters(
            command=py, args=["-m", settings.mcp_server_module], env=env, cwd=cwd)

    async def start(self) -> None:
        if not settings.mcp_enabled:
            self.status, self.error = "disabled", "MCP 未启用（MCP_ENABLED=0）"
            logger.info("MCP 未启用，工具走原生实现")
            return
        try:
            import mcp  # noqa: F401
        except Exception as exc:
            self.status, self.error = "error", f"未安装 mcp SDK：{exc}"
            logger.warning("MCP SDK 不可用，旁路原生工具")
            return
        self._stop_evt = asyncio.Event()
        self._reload_evt = asyncio.Event()
        self._ready_evt = asyncio.Event()
        self._owner = asyncio.create_task(self._run_owner(), name="mcp-owner")
        try:
            await asyncio.wait_for(self._ready_evt.wait(), timeout=30)
        except asyncio.TimeoutError:
            self.status, self.error = "error", "MCP 子进程启动超时"
            logger.warning("MCP 子进程启动超时，旁路原生工具")
        self._health_task = asyncio.create_task(self._health_loop(), name="mcp-health")

    async def stop(self) -> None:
        for task in (self._health_task, self._owner):
            if task is not None and not task.done():
                task.cancel()
        if self._stop_evt is not None:
            self._stop_evt.set()
        for task in (self._health_task, self._owner):
            if task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=8)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
        self.session, self.status = None, "disabled"

    async def _run_owner(self) -> None:
        """连接拥有者：在同一任务内进入/退出上下文；断开后自动重连。"""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        delay = 2
        while self._stop_evt is not None and not self._stop_evt.is_set():
            try:
                async with AsyncExitStack() as stack:
                    self.status, self.error = "starting", ""
                    read, write = await stack.enter_async_context(stdio_client(self._params()))
                    self.session = await stack.enter_async_context(ClientSession(read, write))
                    await self.session.initialize()
                    await self._refresh_tools()
                    import datetime as _dt
                    self.started_at = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.status = "ready"
                    self._ready_evt.set()
                    delay = 2
                    logger.info("MCP 已就绪", extra={"tool": f"tools={len(self._tools)}"})
                    await self._wait_signal()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.session = None
                self.status, self.error = "error", str(exc)[:300]
                if self._ready_evt is not None:
                    self._ready_evt.set()      # 不阻塞启动流程
                if self._stop_evt is not None and not self._stop_evt.is_set():
                    logger.warning("MCP 连接异常，%ss 后重连: %s", delay, exc)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)
        self.session = None
        if self.status == "ready":
            self.status = "disabled"

    async def _wait_signal(self) -> None:
        """等待「停止」或「重连」信号（谁先到算谁的）。"""
        assert self._stop_evt is not None and self._reload_evt is not None
        stop = asyncio.ensure_future(self._stop_evt.wait())
        reload_ = asyncio.ensure_future(self._reload_evt.wait())
        done, pending = await asyncio.wait({stop, reload_},
                                           return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if reload_ in done:
            self._reload_evt.clear()

    async def _refresh_tools(self) -> None:
        res = await self.session.list_tools()
        if not res.tools:
            raise RuntimeError("MCP 返回空工具列表")
        self._tools = [{"name": t.name, "description": t.description or "",
                        "input_schema": t.inputSchema or {}} for t in res.tools]
        self._tool_names = {t["name"] for t in self._tools}
        self.server_name = getattr(res, "serverInfo", None) and "" or self.server_name

    async def reload(self) -> None:
        """主动触发重连（健康检查失败 / 工具调用传输异常时调用）。"""
        self.reloads += 1
        if self._reload_evt is not None:
            self._reload_evt.set()

    # ───────────── 健康检查 ─────────────

    async def _health_loop(self) -> None:
        interval = max(10, int(settings.mcp_health_interval))
        while True:
            try:
                await asyncio.sleep(interval)
                if self._stop_evt is not None and self._stop_evt.is_set():
                    break
                if not self.enabled:
                    continue          # 未就绪时由拥有者任务负责退避重连
                self.checks += 1
                try:
                    # 真实请求探活：能列出工具才算「连接可用」，而非「连接存在」
                    res = await asyncio.wait_for(self.session.list_tools(), timeout=8)
                    if not res.tools:
                        raise RuntimeError("工具列表为空")
                    self._tool_names = {t.name for t in res.tools}
                except Exception as exc:
                    self.failures += 1
                    logger.warning("MCP 健康检查失败（疑似假连接），触发重连: %s", exc)
                    await self.reload()
            except asyncio.CancelledError:
                raise

    # ───────────── 调用 ─────────────

    async def call_tool(self, name: str, arguments: dict | None = None,
                        timeout: float | None = None) -> dict:
        """按 MCP 工具名调用；不可用或传输失败抛 McpUnavailable 供上层回落。"""
        if not self.enabled or self.session is None:
            raise McpUnavailable("MCP 未就绪")
        self.calls += 1
        try:
            res = await asyncio.wait_for(
                self.session.call_tool(name, arguments or {}),
                timeout=timeout or settings.mcp_call_timeout)
        except Exception as exc:
            self.failures += 1
            await self.reload()       # 传输失败按「假连接」处理
            raise McpUnavailable(str(exc)) from exc
        return _extract_result(res)

    async def call_for(self, agent_tool: str, arguments: dict | None = None) -> dict:
        """按智能体侧工具名调用（内部做别名映射）。"""
        return await self.call_tool(TOOL_ALIAS.get(agent_tool, agent_tool), arguments)

    # ───────────── 对外视图 ─────────────

    def tools_view(self) -> list[dict]:
        return [dict(t) for t in self._tools]

    def openai_tools(self) -> list[dict]:
        return [{"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["input_schema"] or {"type": "object", "properties": {}}}}
            for t in self._tools]

    def snapshot(self) -> dict:
        return {
            "enabled": bool(settings.mcp_enabled),
            "status": self.status, "error": self.error,
            "transport": "stdio", "server_module": settings.mcp_server_module,
            "started_at": self.started_at,
            "tools": sorted(self._tool_names),
            "counts": {"tools": len(self._tools), "checks": self.checks,
                       "reloads": self.reloads, "calls": self.calls,
                       "failures": self.failures},
        }


mcp_manager = McpManager()
