"""MCP 链路冒烟：直接以子进程方式验证 mcp-server 可用。

用法（在 backend 目录下）：
    python scripts/smoke_mcp.py

验证点：
  1. 子进程启动 + initialize + list_tools（MCP 协议握手）
  2. 逐个调用工具（天气 / 逆地理编码 / 向量检索 / 闹钟 / 桌面通知）
  3. 健康检查与重连计数
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, ".")
os.environ["MCP_ENABLED"] = "1"


async def main() -> None:
    from app.services.mcp_service.manager import mcp_manager

    await mcp_manager.start()
    snap = mcp_manager.snapshot()
    print("状态:", snap["status"], "| 错误:", snap["error"])
    print("工具:", snap["tools"])
    if not mcp_manager.enabled:
        print("MCP 未就绪，跳过调用测试")
        return

    calls = [
        ("get_weather", {"city": "成都", "days": 2}),
        ("search_poi", {"city": "成都", "topk": 3}),
        ("reverse_geocode", {"lat": 30.5728, "lon": 104.0668}),
        ("search_knowledge", {"query": "成都 熊猫基地 门票", "topk": 3}),
        ("parse_document", {"file_name": "note.txt",
                            "content_base64": __import__("base64").b64encode(
                                "标题\n\n正文内容：门票 50 元。\n- 1 -\n".encode("utf-8")).decode()}),
        ("get_current_time", {}),
        ("set_alarm", {"user_id": 1, "title": "出发提醒", "when": "明天早上8点"}),
        ("notify_desktop", {"user_id": 1, "title": "旅行当天提醒", "content": "今天出发"}),
    ]
    for name, args in calls:
        try:
            res = await mcp_manager.call_tool(name, args)
            brief = json.dumps(res, ensure_ascii=False)[:140]
            print(f"  · {name} → {brief}")
        except Exception as exc:
            print(f"  · {name} 调用失败: {exc}")

    print("计数:", mcp_manager.snapshot()["counts"])
    await mcp_manager.stop()
    print("已关闭")


if __name__ == "__main__":
    asyncio.run(main())
