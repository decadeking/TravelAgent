"""地理坐标：真实城市经纬度（WGS84）与坐标工具。

用于地图定位与真实路线规划。城市坐标为真实值；
景点坐标在真实城市中心基础上做确定性偏移（同一景点坐标稳定），
生产可替换为高德/OSM 的真实 POI 坐标。
"""
from __future__ import annotations

import hashlib

# 真实城市中心坐标（WGS84）
CITY_COORDS: dict[str, tuple[float, float]] = {
    "成都": (30.5728, 104.0668), "北京": (39.9042, 116.4074), "上海": (31.2304, 121.4737),
    "杭州": (30.2741, 120.1551), "西安": (34.3416, 108.9398), "厦门": (24.4798, 118.0894),
    "重庆": (29.5630, 106.5516), "广州": (23.1291, 113.2644), "深圳": (22.5431, 114.0579),
    "南京": (32.0603, 118.7969), "苏州": (31.2989, 120.5853), "武汉": (30.5928, 114.3055),
    "长沙": (28.2282, 112.9388), "青岛": (36.0671, 120.3826), "昆明": (24.8801, 102.8329),
    "丽江": (26.8721, 100.2299), "三亚": (18.2528, 109.5119), "拉萨": (29.6520, 91.1721),
    "桂林": (25.2736, 110.2900), "大理": (25.6065, 100.2676), "哈尔滨": (45.8038, 126.5340),
    "天津": (39.0842, 117.2009), "郑州": (34.7466, 113.6254), "乌鲁木齐": (43.8256, 87.6168),
    "香港": (22.3193, 114.1694), "澳门": (22.1987, 113.5439), "台北": (25.0330, 121.5654),
    "东京": (35.6762, 139.6503), "大阪": (34.6937, 135.5023), "首尔": (37.5665, 126.9780),
    "新加坡": (1.3521, 103.8198), "曼谷": (13.7563, 100.5018), "巴黎": (48.8566, 2.3522),
    "伦敦": (51.5074, -0.1278), "纽约": (40.7128, -74.0060), "罗马": (41.9028, 12.4964),
    "迪拜": (25.2048, 55.2708), "悉尼": (-33.8688, 151.2093),
}

CITY_ALIAS = {
    "chengdu": "成都", "beijing": "北京", "shanghai": "上海", "hangzhou": "杭州",
    "xian": "西安", "xi'an": "西安", "xiamen": "厦门", "sanya": "三亚",
}


def city_coords(city: str) -> tuple[float, float] | None:
    name = (city or "").strip()
    if name in CITY_COORDS:
        return CITY_COORDS[name]
    lowered = name.lower()
    if lowered in CITY_ALIAS:
        return CITY_COORDS[CITY_ALIAS[lowered]]
    for key, val in CITY_COORDS.items():   # 子串匹配（如「成都市」）
        if key and key in name:
            return val
    return None


def poi_coords(city: str, poi_name: str) -> tuple[float, float] | None:
    """在真实城市中心附近生成确定性偏移坐标（同一 POI 稳定）。"""
    base = city_coords(city)
    if base is None:
        return None
    h = hashlib.md5(f"{city}:{poi_name}".encode("utf-8")).digest()
    # 偏移范围约 ±0.06 度（≈ ±6km）
    dlat = (h[0] / 255 - 0.5) * 0.12
    dlon = (h[1] / 255 - 0.5) * 0.12
    return round(base[0] + dlat, 5), round(base[1] + dlon, 5)


def geocode(query: str) -> dict:
    """地名解析：先查内置城市表，未命中再调真实地理编码（Nominatim）。

    这样「成都」这类热点城市零网络即可定位；冷门地名/景点名则走
    OpenStreetMap 的真实地理编码，失败回落为未找到。
    """
    name = (query or "").strip()
    coords = city_coords(name)
    if coords:
        return {"name": name, "lat": coords[0], "lon": coords[1],
                "source": "local-city-table", "found": True}
    from .providers import fetch_geocode
    real = fetch_geocode(name)
    if real:
        return {"name": real.get("display_name") or name,
                "lat": real["lat"], "lon": real["lon"],
                "source": "nominatim-osm", "found": True}
    return {"name": name, "found": False, "source": "local-city-table",
            "tip": "未找到该地名，可换用更常见的城市/景点名，或检查网络"}


def reverse_geocode(lat: float, lon: float) -> dict:
    """逆地理编码：经纬度 → 地名。先就近匹配内置城市表，再调真实服务。

    内置表先匹配可保证「无网络也能给出城市名」，这是位置信息上传的保底路径。
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return {"found": False, "error": "经纬度格式不正确"}
    # 就近匹配内置城市（约 0.6 度内视为同城）
    best, best_dist = "", None
    for name, (clat, clon) in CITY_COORDS.items():
        dist = abs(clat - lat) + abs(clon - lon)
        if best_dist is None or dist < best_dist:
            best, best_dist = name, dist
    if best and best_dist is not None and best_dist <= 0.6:
        return {"name": best, "city": best, "lat": lat, "lon": lon,
                "source": "local-city-table", "found": True,
                "display_name": f"{best}（约 {lat:.4f}, {lon:.4f}）"}
    from .providers import fetch_reverse_geocode
    real = fetch_reverse_geocode(lat, lon)
    if real:
        return {"name": real.get("city") or real["display_name"],
                "city": real.get("city", ""), "district": real.get("district", ""),
                "lat": lat, "lon": lon, "source": "nominatim-osm", "found": True,
                "display_name": real["display_name"]}
    return {"name": f"{lat:.4f}, {lon:.4f}", "lat": lat, "lon": lon,
            "source": "coordinates", "found": False,
            "tip": "网络不可用，已返回原始经纬度"}

