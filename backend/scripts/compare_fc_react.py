"""Function Calling vs ReAct 对照实验（Q10）。

同一组工具、同一批请求，分别走 FC（结构化 tool_calls）与 ReAct（文本
Thought/Action/Observation 循环）两条路径，对比四个维度：
成功率、平均时延、平均 token 消耗、可解释性（步数）。

离线 mock 模式即可运行；接真实模型后结果更具说服力。
用法（backend 目录）：python scripts/compare_fc_react.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.agent_service.core.graph import travel_graph  # noqa: E402
from app.services.agent_service.core.react import react_run  # noqa: E402
from app.services.tool_service import tools  # noqa: E402

REQUESTS = [
    "我要去成都玩4天，预算3000元",
    "我想去北京玩3天，预算2500元",
    "去杭州玩2天，预算1500元",
    "西安4天，预算3000元，喜欢历史",
    "厦门3天，预算2000元，带小孩",
]


async def _noop(_e, _d):
    return None


async def run_fc(text: str) -> dict:
    state = {"messages": [{"role": "user", "content": text}],
             "slots": {}, "tool_results": {}, "citations": [], "warnings": [],
             "token_usage": {"prompt_tokens": 0, "completion_tokens": 0}}
    start = time.perf_counter()
    async def _emit(e, d):
        await _noop(e, d)
    out = await travel_graph.run(state, emit=_emit)
    ms = (time.perf_counter() - start) * 1000
    usage = out.get("token_usage", {})
    return {"success": bool(out.get("plan_draft")), "latency_ms": ms,
            "tokens": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            "tools": len(out.get("tool_results", {})), "steps": 6}


async def run_react(text: str) -> dict:
    start = time.perf_counter()
    out = await react_run(text)
    ms = (time.perf_counter() - start) * 1000
    usage = out.get("usage", {})
    return {"success": out["success"], "latency_ms": ms,
            "tokens": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            "tools": len(out.get("tool_results", {})), "steps": out.get("steps", 0)}


async def main() -> None:
    fc_rows, react_rows = [], []
    for text in REQUESTS:
        fc_rows.append(await run_fc(text))
        react_rows.append(await run_react(text))

    def _avg(rows, key):
        return sum(r[key] for r in rows) / len(rows)

    print(json.dumps({
        "n": len(REQUESTS),
        "function_calling": {
            "success_rate": f"{sum(r['success'] for r in fc_rows)/len(fc_rows):.0%}",
            "avg_latency_ms": round(_avg(fc_rows, "latency_ms"), 1),
            "avg_tokens": round(_avg(fc_rows, "tokens"), 1),
            "avg_tools": round(_avg(fc_rows, "tools"), 1),
        },
        "react": {
            "success_rate": f"{sum(r['success'] for r in react_rows)/len(react_rows):.0%}",
            "avg_latency_ms": round(_avg(react_rows, "latency_ms"), 1),
            "avg_tokens": round(_avg(react_rows, "tokens"), 1),
            "avg_steps": round(_avg(react_rows, "steps"), 1),
        },
        "note": "FC 结构化输出省文本解析与 Thought token；ReAct 可解释性更强",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
