"""tool-service：函数工具层。

统一封装 天气 / 景点(POI) / 路线 / 预算 / 自由搜索 五类工具。
- 每个工具都用 JSON Schema 注册（供大模型 Function Calling）
- 统一处理链路：参数校验 → 超时 → 重试 → 熔断 → 兜底 mock
- 从本地 JSON 读取 mock 数据，答辩现场不依赖外网与第三方 Key
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Union

from . import geo, providers

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _load(name: str, default: Any) -> Any:
    try:
        with open(_DATA_DIR / name, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


_POI: dict[str, list[dict]] = _load("poi.json", {})
_KB: list[dict] = _load("knowledge_base.json", [])

_CONDITIONS = ["晴", "多云", "阴", "小雨", "阵雨", "晴转多云"]
_CATEGORY_LABEL = {
    "culture": "人文", "nature": "自然", "food": "美食",
    "shopping": "购物", "entertainment": "娱乐", "museum": "博物馆",
    "sightseeing": "观光",
}


def _seed(*parts: str) -> random.Random:
    h = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()
    return random.Random(int(h[:8], 16))


def list_cities() -> list[str]:
    return sorted(_POI.keys())


# ─────────────────────────── 工具实现 ───────────────────────────

def get_weather(city: str, days: int = 3, start_date: str | None = None) -> dict:
    """查询目的地未来数日天气：优先真实数据（Open-Meteo），失败回落 mock。"""
    city = (city or "").strip()
    days = max(1, min(int(days or 3), 7))

    real = providers.fetch_weather(city, days)
    if real and real.get("forecast"):
        return real

    base = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.now()
    rnd = _seed("weather", city)
    forecast = []
    for i in range(days):
        d = base + timedelta(days=i)
        rnd.seed(hash((city, d.strftime("%Y-%m-%d"))) & 0xFFFFFFFF)
        cond = rnd.choice(_CONDITIONS)
        high = rnd.randint(18, 32) if cond not in ("小雨", "阵雨") else rnd.randint(15, 26)
        low = high - rnd.randint(5, 10)
        forecast.append({
            "date": d.strftime("%Y-%m-%d"),
            "condition": cond,
            "high": high,
            "low": low,
            "suggestion": "适合户外游览" if cond in ("晴", "多云", "晴转多云") else "建议备好雨具",
        })
    return {"city": city, "source": "mock", "forecast": forecast}


def search_poi(city: str, keyword: str = "", category: str = "",
               topk: int = 8) -> dict:
    """按城市 + 关键词/类别检索景点。"""
    city = (city or "").strip()
    pois = _POI.get(city, [])
    if not pois:
        # 未知城市：返回通用建议
        return {"city": city, "source": "mock", "items": [],
                "tip": f"暂未收录「{city}」的景点数据，可切换成都/北京/上海/杭州/西安/厦门体验"}
    result = []
    for p in pois:
        if category and p.get("category") != category:
            continue
        if keyword and keyword not in p["name"] and keyword not in "".join(p.get("tags", [])):
            continue
        item = dict(p)
        item["category_label"] = _CATEGORY_LABEL.get(p.get("category", ""), p.get("category", ""))
        coords = geo.poi_coords(city, p["name"])
        if coords:
            item["lat"] = coords[0]
            item["lon"] = coords[1]
        result.append(item)
    result.sort(key=lambda x: -x.get("rating", 0))
    center = geo.city_coords(city)
    return {"city": city, "source": "curated-dataset", "items": result[:max(1, int(topk))],
            "center": ({"lat": center[0], "lon": center[1]} if center else None)}


def plan_route(from_poi: str, to_poi: str, city: str = "") -> dict:
    """估算两点间通行时间与费用。

    若两端均为已知城市，则调用 OSRM 真实驾车路线；否则用市内通行 mock。
    """
    if from_poi in geo.CITY_COORDS and to_poi in geo.CITY_COORDS:
        real = providers.fetch_route(from_poi, to_poi)
        if real:
            a = geo.city_coords(from_poi)
            b = geo.city_coords(to_poi)
            real["from_coords"] = {"lat": a[0], "lon": a[1]}
            real["to_coords"] = {"lat": b[0], "lon": b[1]}
            return real

    rnd = _seed("route", city, from_poi, to_poi)
    distance_km = round(rnd.uniform(2.0, 25.0), 1)
    if distance_km <= 3:
        mode, minutes, cost = "步行/地铁", int(distance_km * 12), 3
    elif distance_km <= 12:
        mode, minutes, cost = "地铁", int(distance_km * 4) + 8, 5
    else:
        mode, minutes, cost = "打车", int(distance_km * 2.2) + 6, round(2.4 * distance_km + 10, 1)
    a = geo.poi_coords(city, from_poi)
    b = geo.poi_coords(city, to_poi)
    out = {
        "from": from_poi, "to": to_poi, "city": city, "source": "mock",
        "distance_km": distance_km, "duration_min": minutes,
        "transport": mode, "cost": cost,
    }
    if a and b:
        out["from_coords"] = {"lat": a[0], "lon": a[1]}
        out["to_coords"] = {"lat": b[0], "lon": b[1]}
    return out


def geocode(query: str) -> dict:
    """地名定位：返回真实经纬度（内置城市坐标表）。"""
    return geo.geocode(query)


def reverse_geocode(lat: float, lon: float) -> dict:
    """逆地理编码：经纬度 → 地名（用户上传位置信息时使用）。"""
    return geo.reverse_geocode(lat, lon)


def _current_time(city: str = "") -> dict:
    """当前真实时间（服务器时钟），并给出常见时区提示。"""
    now = datetime.now()
    weekday = "一二三四五六日"[now.weekday()]
    return {"city": city, "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"), "weekday": f"周{weekday}",
            "iso": now.isoformat(timespec="seconds"), "source": "server-clock"}


get_current_time = _current_time      # 公开名（供测试与直接调用）


def estimate_budget(city: str, days: int, budget: float = 0.0,
                    travel_style: str = "comfort", travelers: int = 1,
                    poi_names: list[str] | None = None) -> dict:
    """门票 + 餐饮 + 住宿 + 市内交通 费用拆分（本地规则引擎）。"""
    days = max(1, int(days or 1))
    travelers = max(1, int(travelers or 1))
    pois = _POI.get(city, [])
    ticket = sum(p.get("ticket", 0) for p in pois
                 if not poi_names or p["name"] in poi_names) * travelers
    hotel_per_night = {"budget": 180, "comfort": 380, "luxury": 900}.get(travel_style, 380)
    meal_per_day = {"budget": 80, "comfort": 150, "luxury": 320}.get(travel_style, 150)
    hotel = hotel_per_night * max(1, days - 1) * max(1, (travelers + 1) // 2)
    meals = meal_per_day * days * travelers
    transport = 40 * days * travelers
    total = ticket + hotel + meals + transport
    return {
        "city": city, "days": days, "travelers": travelers, "travel_style": travel_style,
        "source": "local-rules",
        "breakdown": {
            "ticket": round(ticket, 1),
            "hotel": round(hotel, 1),
            "meals": round(meals, 1),
            "transport": round(transport, 1),
        },
        "total": round(total, 1),
        "budget": budget,
        "within_budget": (total <= budget) if budget else True,
        "over_budget": round(max(0.0, total - budget), 1) if budget else 0.0,
    }


def web_search(query: str, topk: int = 3) -> dict:
    """自由搜索（本地固定语料，用于补充长尾信息）。"""
    q = (query or "").strip()
    hits = [k for k in _KB if q and (q in k["title"] or q in k["content"])
            or any(tok and tok in k["title"] + k["content"] for tok in q.split())]
    if not hits:
        hits = _KB[:topk]
    return {"query": q, "source": "mock",
            "items": [{"title": h["title"], "snippet": h["content"][:120]} for h in hits[:topk]]}


# ─────────────────── 工具注册表（JSON Schema，供 Function Calling） ───────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询某城市未来数日的天气预报",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如 成都"},
                    "days": {"type": "integer", "description": "查询天数，1-7"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_poi",
            "description": "按城市与关键词/类别检索景点",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "keyword": {"type": "string"},
                    "category": {"type": "string",
                                 "enum": ["culture", "nature", "food", "shopping",
                                          "entertainment", "museum", "sightseeing"]},
                    "topk": {"type": "integer"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_route",
            "description": "估算两个地点之间的通行时间与费用",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_poi": {"type": "string"},
                    "to_poi": {"type": "string"},
                    "city": {"type": "string"},
                },
                "required": ["from_poi", "to_poi"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_budget",
            "description": "估算行程费用拆分（门票/住宿/餐饮/交通）",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "days": {"type": "integer"},
                    "budget": {"type": "number"},
                    "travel_style": {"type": "string", "enum": ["budget", "comfort", "luxury"]},
                    "travelers": {"type": "integer"},
                },
                "required": ["city", "days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索旅行攻略与长尾信息",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "topk": {"type": "integer"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "geocode",
            "description": "把城市或地名解析为真实经纬度坐标，用于地图定位",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "城市或地名"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前真实日期与时间（用于计算出发倒计时、安排未来行程）",
            "parameters": {"type": "object", "properties": {
                "city": {"type": "string", "description": "可选，城市名（用于时区提示）"}},
                "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "为用户创建未来行程提醒（如出发前、集合时间、航班提醒）",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "提醒事项，如「成都出发去机场」"},
                    "when": {"type": "string",
                             "description": "提醒时间，支持「明天早上8点」「3天后」「2026-11-01 09:00」"},
                    "detail": {"type": "string", "description": "补充说明，可留空"},
                },
                "required": ["title", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reverse_geocode",
            "description": "把经纬度解析为可读地名（用户上传位置信息时用于定位所在城市）",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "纬度"},
                    "lon": {"type": "number", "description": "经度"},
                },
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "向量库检索：从知识库（RAG）中召回与查询最相关的攻略片段，用于补充事实依据",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索问题，如「成都 熊猫基地 门票」"},
                    "city": {"type": "string", "description": "可选，限定城市"},
                    "topk": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify_desktop",
            "description": "向用户推送桌面通知（旅行当天/出发前提醒），会同时写入站内消息",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "通知标题"},
                    "content": {"type": "string", "description": "通知正文，可留空"},
                    "link": {"type": "string", "description": "点击后跳转的站内路径，可留空"},
                },
                "required": ["title"],
            },
        },
    },
]

TOOL_FUNCS = {
    "get_weather": get_weather,
    "search_poi": search_poi,
    "plan_route": plan_route,
    "estimate_budget": estimate_budget,
    "web_search": web_search,
    "geocode": geocode,
    "reverse_geocode": reverse_geocode,
    "get_current_time": lambda city="": _current_time(city),
}


def call_tool(name: str, arguments: dict) -> dict:
    """按名称分发工具调用（带 schema 白名单）。"""
    func = TOOL_FUNCS.get(name)
    if func is None:
        return {"error": f"未知工具: {name}"}
    try:
        return func(**arguments)
    except TypeError as exc:
        return {"error": f"参数不合法: {exc}"}


# ─────────────────── 参数二次校验（Q9：模型返回参数不合法怎么办） ───────────────────

_SCHEMA_BY_NAME = {s["function"]["name"]: s["function"]["parameters"] for s in TOOL_SCHEMAS}
_TYPE_MAP = {"string": str, "integer": int, "number": Union[int, float], "boolean": bool}
_MODEL_CACHE: dict[str, type] = {}


def _build_model(name: str) -> type:
    """按工具 JSON Schema 动态构建 Pydantic 校验模型（含枚举白名单）。"""
    from pydantic import create_model

    if name in _MODEL_CACHE:
        return _MODEL_CACHE[name]
    schema = _SCHEMA_BY_NAME[name]
    props: dict = schema.get("properties", {})
    required: list = schema.get("required", [])
    field_defs: dict[str, tuple] = {}
    for fname, spec in props.items():
        py_t = _TYPE_MAP.get(spec.get("type", "string"), str)
        if fname in required:
            field_defs[fname] = (py_t, ...)
        else:
            default = "" if py_t is str else (0 if py_t is int else 0.0 if py_t is float else None)
            field_defs[fname] = (py_t, spec.get("default", default))
        if spec.get("enum"):
            from typing import Literal
            field_defs[fname] = (Literal[tuple(spec["enum"])],  # type: ignore[misc]
                                 spec.get("default", ""))
    cls = create_model(f"{name}_Args", **field_defs)  # type: ignore[misc]
    _MODEL_CACHE[name] = cls
    return cls


def validate_tool_args(name: str, arguments: dict) -> tuple[dict | None, str | None]:
    """用工具的 JSON Schema 对模型给出的参数做 Pydantic 二次校验。

    校验项：未知工具、必填字段缺失、类型不符、枚举白名单（景点类别、住宿档位等）。
    返回 (规范化后的参数字典, 错误信息)；错误信息非空时参数为 None，
    上层据此把错误回喂给模型重新生成（最多 2 次）。
    """
    from pydantic import ValidationError

    if name not in _SCHEMA_BY_NAME:
        return None, f"未知工具 {name}，可用工具：{', '.join(_SCHEMA_BY_NAME)}"
    model_cls = _build_model(name)
    required: list = _SCHEMA_BY_NAME[name].get("required", [])
    try:
        m = model_cls(**(arguments or {}))
    except ValidationError as exc:
        return None, "参数校验失败：" + "; ".join(
            f"{f}: {msg}" for e in exc.errors()
            for f, msg in [(".".join(str(p) for p in e["loc"]) or "参数", e["msg"])])[:300]
    except TypeError as exc:
        return None, f"参数校验失败：{exc}"
    data = m.model_dump()
    # 必填字段非空校验（模型可能给空串）
    for f in required:
        if data.get(f) in (None, ""):
            return None, f"必填字段 {f} 不能为空"
    return data, None


# ─────────────────── 工具结果压缩（Q9：返回值先压缩再回喂，省 token） ───────────────────

def compress_tool_result(name: str, result: dict) -> dict:
    """只保留必要字段，丢弃坐标、来源标注等对模型无用的大字段。"""
    if not isinstance(result, dict) or result.get("error"):
        return result
    if name == "search_poi":
        items = [{"name": i.get("name"), "category": i.get("category"),
                  "ticket": i.get("ticket"), "rating": i.get("rating"),
                  "duration_min": i.get("duration_min"), "note": (i.get("note") or "")[:40],
                  "tags": i.get("tags", [])[:3]}
                 for i in result.get("items", [])][:8]
        return {"city": result.get("city"), "items": items}
    if name == "get_weather":
        fc = [{"date": f.get("date"), "condition": f.get("condition"),
               "low": f.get("low"), "high": f.get("high")}
              for f in result.get("forecast", [])]
        return {"city": result.get("city"), "forecast": fc}
    if name == "plan_route":
        return {k: result.get(k) for k in ("from", "to", "distance_km", "duration_min",
                                           "transport", "cost")}
    if name == "estimate_budget":
        return {"total": result.get("total"), "breakdown": result.get("breakdown"),
                "within_budget": result.get("within_budget")}
    if name == "web_search":
        return {"query": result.get("query"),
                "items": [{"title": i.get("title"), "snippet": (i.get("snippet") or "")[:80]}
                          for i in result.get("items", [])][:3]}
    if name == "get_current_time":
        return {k: result.get(k) for k in ("date", "time", "weekday")}
    if name == "set_reminder":
        return {k: result.get(k) for k in ("reminder_id", "title", "remind_at", "hint")}
    if name == "reverse_geocode":
        return {k: result.get(k) for k in ("name", "city", "lat", "lon", "found", "source")}
    if name == "search_knowledge":
        return {"backend": result.get("backend"), "chunks": result.get("chunks"),
                "items": [{"title": i.get("title"), "score": i.get("score"),
                           "text": (i.get("text") or "")[:160]}
                          for i in (result.get("items") or [])][:5]}
    if name == "notify_desktop":
        return {k: result.get(k) for k in ("title", "desktop_shown", "hint")}
    return result
