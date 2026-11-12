"""真实第三方数据源适配（无 Key 免费接口）+ 失败自动降级。

- 天气：Open-Meteo（https://open-meteo.com）实时预报，无需 Key
- 路线：OSRM 公共路由服务（http://project-osrm.org）真实驾车距离/时长
接口不可用时返回 None，由上层回落到本地 mock，保证演示不中断。
"""
from __future__ import annotations

import httpx

from .geo import city_coords

_UA = {"User-Agent": "TravelAgentDemo/1.0 (+https://example.com)"}

# WMO weather code → 中文
_WMO = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 56: "冻雨", 57: "冻雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "阵雨", 82: "强阵雨", 85: "阵雪", 86: "阵雪",
    95: "雷阵雨", 96: "雷暴冰雹", 99: "雷暴冰雹",
}


def fetch_weather(city: str, days: int = 3) -> dict | None:
    """调用 Open-Meteo 获取真实未来天气。失败返回 None。"""
    coords = city_coords(city)
    if not coords:
        return None
    lat, lon = coords
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Shanghai", "forecast_days": max(1, min(days, 7)),
    }
    try:
        resp = httpx.get(url, params=params, headers=_UA, timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    rains = daily.get("precipitation_probability_max") or []
    forecast = []
    for i, d in enumerate(dates):
        code = int(codes[i]) if i < len(codes) else 0
        cond = _WMO.get(code, "多云")
        rain = int(rains[i]) if i < len(rains) else 0
        forecast.append({
            "date": d, "condition": cond,
            "high": round(highs[i]) if i < len(highs) else None,
            "low": round(lows[i]) if i < len(lows) else None,
            "precipitation_probability": rain,
            "suggestion": ("建议备好雨具" if rain >= 50 else "适合户外游览"),
        })
    return {"city": city, "source": "open-meteo", "coordinates": {"lat": lat, "lon": lon},
            "forecast": forecast}


def fetch_route(from_city: str, to_city: str) -> dict | None:
    """调用 OSRM 获取真实驾车距离与时长。"""
    c1 = city_coords(from_city)
    c2 = city_coords(to_city)
    if not c1 or not c2:
        return None
    lat1, lon1 = c1
    lat2, lon2 = c2
    url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    try:
        resp = httpx.get(url, params={"overview": "false"}, headers=_UA, timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
        route = (data.get("routes") or [{}])[0]
        distance_km = round(route.get("distance", 0) / 1000, 1)
        duration_min = int(route.get("duration", 0) / 60)
    except Exception:
        return None
    return {
        "from": from_city, "to": to_city, "source": "osrm",
        "distance_km": distance_km, "duration_min": duration_min,
        "transport": "驾车", "cost": round(2.4 * distance_km + 10, 1),
    }


def fetch_geocode(query: str) -> dict | None:
    """真实地理编码：OpenStreetMap Nominatim（免费，无需 Key）。

    返回 {lat, lon, display_name}；网络不可用或未命中返回 None。
    """
    name = (query or "").strip()
    if not name:
        return None
    try:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": name, "format": "json", "limit": 1, "accept-language": "zh-CN"},
            headers=_UA, timeout=8.0)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return None
    if not rows:
        return None
    top = rows[0]
    try:
        return {"lat": round(float(top["lat"]), 5), "lon": round(float(top["lon"]), 5),
                "display_name": top.get("display_name", name)}
    except (KeyError, TypeError, ValueError):
        return None


def fetch_reverse_geocode(lat: float, lon: float) -> dict | None:
    """逆地理编码：经纬度 → 可读地名（Nominatim，免费无 Key）。

    用于「上传位置信息」——用户授权浏览器定位后，把坐标还原成地名喂给智能体。
    网络不可用时返回 None，由上层退化为「经纬度文本」。
    """
    try:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "accept-language": "zh-CN"},
            headers=_UA, timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    name = (data.get("display_name") or "").strip()
    if not name:
        return None
    addr = data.get("address") or {}
    return {"display_name": name,
            "city": addr.get("city") or addr.get("town") or addr.get("state") or "",
            "district": addr.get("suburb") or addr.get("county") or ""}

