"""AgentCore 状态图定义。

主链路：intake → plan → tool_call → reflect → respond，
其中 clarify 处理槽位缺失、reflect 的修订回环实现「自检—修订」闭环。
"""
from __future__ import annotations

from . import nodes
from .state_graph import END, StateGraph


def _slots_complete(state: dict) -> bool:
    """只要有目的地就能规划：天数默认 3、预算未填按不限处理。

    仅在「目的地缺失」时才反问——避免因天数/预算没说就整段走模板、
    完全不调用模型与 RAG（这会让用户误以为系统在输出模板数据）。
    """
    sl = state.get("slots", {})
    return bool(sl.get("destination"))


def _after_intake(state: dict) -> str:
    """三条去路：设置提醒 / 目的地明确→规划 / 目的地缺失→反问。

    注意：提醒意图只看「本轮原话」——即使会话里已带着上一轮的目的地槽位，
    本轮说「提醒我…」也应走提醒分支，而不是被历史槽位带去规划行程。
    """
    last = state.get("messages", [])[-1]["content"] if state.get("messages") else ""
    if nodes.is_reminder_intent(last):
        return "reminder"
    if _slots_complete(state):
        return "plan"
    return "clarify"


def _after_reflect(state: dict) -> str:
    return "revise" if state.get("_revise") else "done"


def build_travel_graph() -> StateGraph:
    g = StateGraph("travel_planner", max_steps=24)
    g.add_node("intake", nodes.intake)
    g.add_node("clarify", nodes.clarify)
    g.add_node("reminder", nodes.reminder)
    g.add_node("plan", nodes.plan)
    g.add_node("tool_call", nodes.tool_call)
    g.add_node("reflect", nodes.reflect)
    g.add_node("respond", nodes.respond)

    g.set_entry_point("intake")
    g.add_conditional_edges("intake", _after_intake,
                            {"plan": "plan", "clarify": "clarify", "reminder": "reminder"})
    g.add_edge("clarify", END)
    g.add_edge("reminder", "respond")
    g.add_edge("plan", "tool_call")
    g.add_edge("tool_call", "reflect")
    g.add_conditional_edges("reflect", _after_reflect, {"revise": "plan", "done": "respond"})
    g.add_edge("respond", END)
    return g


travel_graph = build_travel_graph()
