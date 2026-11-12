"""轻量状态图引擎（对齐 LangGraph 的核心语义）。

为什么自研而不直接依赖 langgraph：
- 环境无法保证 langgraph 及其重依赖可安装，且离线演示需要零外部依赖；
- 本引擎实现了与 LangGraph 同构的关键语义：节点(node)、条件边(conditional edge)、
  checkpointer(状态持久化)、interrupt(human-in-the-loop 暂停点)，接口形状一致，
  生产需要时可平滑迁移到 langgraph.graph.StateGraph。

三个关键设计：
1. 节点是「异步函数」，接收 (state, emit)，返回状态增量(dict)；
2. 条件边按状态路由，支持回环（reflect → plan 的修订循环，用 revision_count 封顶）；
3. checkpointer 在每个节点执行后持久化状态，多轮会话与断线恢复天然成立。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

NodeFn = Callable[[dict, Callable[[str, Any], Awaitable[None]]], Awaitable[dict | None]]
RouterFn = Callable[[dict], str]

END = "__end__"


class StateGraph:
    def __init__(self, name: str = "graph", max_steps: int = 24) -> None:
        self.name = name
        self.max_steps = max_steps
        self._nodes: dict[str, NodeFn] = {}
        self._edges: dict[str, str] = {}
        self._cond: dict[str, tuple[RouterFn, dict[str, str]]] = {}
        self._entry: str | None = None

    # ---- 构图 API ----
    def add_node(self, name: str, fn: NodeFn) -> "StateGraph":
        self._nodes[name] = fn
        return self

    def add_edge(self, src: str, dst: str) -> "StateGraph":
        self._edges[src] = dst
        return self

    def add_conditional_edges(self, src: str, router: RouterFn,
                              mapping: dict[str, str]) -> "StateGraph":
        self._cond[src] = (router, mapping)
        return self

    def set_entry_point(self, name: str) -> "StateGraph":
        self._entry = name
        return self

    # ---- 执行 ----
    async def run(
        self,
        state: dict,
        emit: Callable[[str, Any], Awaitable[None]] | None = None,
        checkpointer: Callable[[dict], Awaitable[None]] | None = None,
    ) -> dict:
        async def _noop(_t: str, _p: Any) -> None:
            return None

        emit = emit or _noop
        current = self._entry
        steps = 0
        while current and current != END:
            if steps >= self.max_steps:
                state.setdefault("warnings", []).append("达到最大步数上限，提前结束")
                break
            steps += 1
            node = self._nodes[current]
            await emit("node", {"node": current, "step": steps})
            update = await node(state, emit)
            if update:
                state.update(update)
            if checkpointer:
                await checkpointer(state)
            current = self._next(current, state)
        return state

    def _next(self, node: str, state: dict) -> str:
        if node in self._cond:
            router, mapping = self._cond[node]
            return mapping.get(router(state), END)
        return self._edges.get(node, END)
