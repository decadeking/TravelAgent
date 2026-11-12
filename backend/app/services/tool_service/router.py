"""tool-service 路由：对外暴露统一工具接口（前端详情页也复用）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from ...schemas.common import ok
from . import tools

router = APIRouter(prefix="/api/tools", tags=["tool-service"])


@router.get("/cities")
async def cities():
    return ok(tools.list_cities())


@router.get("/weather")
async def weather(city: str = Query(...), days: int = 3):
    # 真实数据源为同步 HTTP 调用，放入线程池避免阻塞事件循环
    return ok(await asyncio.to_thread(tools.get_weather, city, days))


@router.get("/poi")
async def poi(city: str = Query(...), keyword: str = "", category: str = "", topk: int = 8):
    return ok(tools.search_poi(city, keyword, category, topk))


@router.get("/route")
async def route(from_poi: str = Query(...), to_poi: str = Query(...), city: str = ""):
    return ok(await asyncio.to_thread(tools.plan_route, from_poi, to_poi, city))


@router.get("/geocode")
async def geocode(query: str = Query(...)):
    return ok(tools.geocode(query))


@router.get("/reverse_geocode")
async def reverse_geocode(lat: float = Query(...), lon: float = Query(...)):
    """逆地理编码：经纬度 → 地名（规划页「上传位置信息」使用）。"""
    return ok(await asyncio.to_thread(tools.reverse_geocode, lat, lon))


@router.get("/schemas")
async def schemas():
    """返回全部工具 JSON Schema（供调试 / 前端展示 Function Calling 定义）。"""
    return ok(tools.TOOL_SCHEMAS)
