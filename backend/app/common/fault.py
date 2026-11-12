"""故障注入开关（用于熔断/降级的故障演练与自动化测试）。

对齐设计中的「故障演练」：用 mock 层注入故障——
模拟大模型超时/500、模拟工具宕机，观察熔断打开与降级响应。
可通过 /api/admin/fault 动态开关，答辩现场可直接演示。
"""
from __future__ import annotations


class FaultInjector:
    def __init__(self) -> None:
        self.model_down: bool = False        # 模拟大模型不可用
        self.tool_down: set[str] = set()     # 模拟指定工具宕机

    def snapshot(self) -> dict:
        return {"model_down": self.model_down, "tool_down": sorted(self.tool_down)}

    def reset(self) -> None:
        self.model_down = False
        self.tool_down.clear()


fault = FaultInjector()
