"""MCP server（stdio 子进程）：把旅行能力统一封装成 MCP 工具。

工具清单（供任意兼容 MCP 的客户端发现与调用）：
  地图/天气类  get_weather / search_poi / geocode / reverse_geocode / plan_route
  费用类      estimate_budget
  prompt-time get_current_time / set_alarm（定时闹钟）
  通知类      notify_desktop（desktop-notification）
  知识检索    search_knowledge（向量库检索 / RAG）

启动方式（由 manager 拉起子进程，也可手工调试）：
    python -m app.services.mcp_service.server

说明：本进程通过 stdio 与父进程交换 JSON-RPC，任何日志都不能写 stdout
（FastMCP 已把 stdio 交给协议层，日志统一走 stderr）。
"""
from __future__ import annotations

import os

# stdio 传输下 stdout 是 JSON-RPC 协议帧，日志必须改道 stderr（需在导入业务模块前设置）
os.environ.setdefault("LOG_TO_STDERR", "1")

from mcp.server.fastmcp import FastMCP  # noqa: E402

from ..tool_service import tools  # noqa: E402
from .desktop import show_toast  # noqa: E402

mcp = FastMCP("travel-agent")


# ───────────────────── 地图 / 天气 / 路线 ─────────────────────

@mcp.tool()
def get_weather(city: str, days: int = 3) -> dict:
    """查询城市未来数日天气。数据源 Open-Meteo（真实），失败回落本地 fork。"""
    return tools.get_weather(city, days)


@mcp.tool()
def search_poi(city: str, keyword: str = "", category: str = "", topk: int = 8) -> dict:
    """地图地点 API：按城市与关键词/类别检索景点与门票信息。"""
    return tools.search_poi(city, keyword, category, topk)


@mcp.tool()
def geocode(query: str) -> dict:
    """地图地点 API：把城市或地名解析为真实经纬度坐标。"""
    return tools.geocode(query)


@mcp.tool()
def reverse_geocode(lat: float, lon: float) -> dict:
    """逆地理编码：把经纬度解析为可读地名（用户上传位置信息时使用）。"""
    return tools.reverse_geocode(lat, lon)


@mcp.tool()
def plan_route(from_poi: str, to_poi: str, city: str = "") -> dict:
    """估算两点通行时间与费用；两端为已知城市时调用 OSRM 真实驾车路线。"""
    return tools.plan_route(from_poi, to_poi, city)


@mcp.tool()
def estimate_budget(city: str, days: int, budget: float = 0.0,
                    travel_style: str = "comfort", travelers: int = 1) -> dict:
    """费用估算：门票 + 住宿 + 餐饮 + 市内交通拆分。"""
    return tools.estimate_budget(city, days, budget, travel_style, travelers)


@mcp.tool()
def get_current_time(city: str = "") -> dict:
    """prompt-time：获取当前真实日期与时间（服务器时钟）。"""
    return tools.get_current_time(city)


# ───────────────────── 文档解析（pdf / wps(docx) / txt / md） ─────────────────────

@mcp.tool()
def parse_document(file_name: str, content_base64: str) -> dict:
    """文档解析与原料清洗：pdf（pdfplumber）/ wps·Word（python-docx）/ txt / md。

    入参为文件的 base64 内容，返回清洗后的纯文本与统计（不写库），
    供调用方统一复用同一套解析能力，避免各服务各自实现。
    """
    import base64

    from ..media_service.parsers import parse_document as _parse
    try:
        raw = base64.b64decode(content_base64 or "", validate=False)
    except Exception as exc:
        return {"ok": False, "error": f"文件内容解码失败：{exc}"}
    return _parse(file_name, raw)


# ───────────────────── 向量库检索（RAG） ─────────────────────

@mcp.tool()
async def search_knowledge(query: str, city: str = "", topk: int = 5) -> dict:
    """向量库检索：从 RAG 知识库召回与查询最相关的片段（含来源溯源）。"""
    from ..agent_service.rag.retriever import retriever
    hits = await retriever.retrieve(query, city=city or None, topk=topk)
    return {"query": query, "backend": retriever.backend,
            "chunks": retriever.chunk_count, "items": hits}


# ───────────────────── prompt-time 闹钟 / 桌面通知 ─────────────────────

@mcp.tool()
async def set_alarm(user_id: int, title: str, when: str, detail: str = "") -> dict:
    """prompt-time 闹钟：为指定用户创建定时提醒（出发前、集合时间、航班提醒等）。

    when 支持「明天早上8点」「3天后」「2026-11-01 09:00」等自然语言。
    """
    from ..agent_service.reminders import create_reminder
    return await create_reminder(user_id=user_id or None, title=title,
                                 when=when, detail=detail)


@mcp.tool()
async def notify_desktop(user_id: int, title: str, content: str = "",
                         link: str = "", write_notification: bool = True) -> dict:
    """desktop-notification：向用户推送桌面气泡提醒。

    write_notification=True 时同时写入站内通知；调用方若已写站内通知，
    可传 False 以避免重复。
    """
    from ...db.models import Notification
    from ...db.session import SessionLocal
    if not user_id:
        return {"error": "缺少用户身份，未能推送通知"}
    if write_notification:
        async with SessionLocal() as db:
            db.add(Notification(user_id=user_id, kind="reminder",
                                title=(title or "行程提醒")[:200],
                                content=(content or "")[:500], link=(link or "")[:255]))
            await db.commit()
    shown = show_toast(title, content)
    return {"user_id": user_id, "title": title, "desktop_shown": shown,
            "hint": f"已提醒：{title}"}


if __name__ == "__main__":
    mcp.run()          # 默认 stdio 传输
