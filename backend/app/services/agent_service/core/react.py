"""ReAct 对照实现（Q10：与 Function Calling 做对照实验）。

ReAct 用 Prompt 模板驱动 Thought → Action → Observation 循环，是文本层面的推理；
Function Calling 是模型原生的结构化输出能力。本模块用同一组工具实现 ReAct 版本，
供 scripts/compare_fc_react.py 做对照实验（成功率 / 时延 / token 消耗 / 可解释性）。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from ...tool_service import tools

REACT_SYSTEM = """你是旅行规划助手，按 ReAct 格式工作，每步输出：
Thought: 你的思考
Action: 工具名[参数名=值, 参数名=值]
系统会返回 Observation: 工具结果。信息足够后输出：
Final Answer: 给用户的答复
可用工具：get_weather[city=,days=]、search_poi[city=,topk=]、estimate_budget[city=,days=,budget=]"""

_ACTION_RE = re.compile(r"Action:\s*(\w+)\[([^\]]*)\]")
_FINAL_RE = re.compile(r"Final Answer:\s*(.+)", re.S)


def parse_action(text: str) -> tuple[str, dict] | None:
    """解析模型文本里的 Action 行，返回 (工具名, 参数字典)。"""
    m = _ACTION_RE.search(text or "")
    if not m:
        return None
    name = m.group(1)
    args: dict[str, Any] = {}
    for pair in m.group(2).split(","):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        if re.fullmatch(r"-?\d+", v):
            args[k] = int(v)
        elif re.fullmatch(r"-?\d+\.\d+", v):
            args[k] = float(v)
        else:
            args[k] = v
    return name, args


async def react_run(user_content: str, *, max_steps: int = 6,
                    model: str | None = None, api_key: str | None = None) -> dict:
    """跑一轮 ReAct 循环，返回 {success, answer, tool_results, usage, steps}。"""
    from ..llm.adapter import llm

    messages = [{"role": "system", "content": REACT_SYSTEM},
                {"role": "user", "content": user_content}]
    results: dict[str, Any] = {}
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for step in range(1, max_steps + 1):
        res = await llm.chat(messages, tools=None, model=model, api_key=api_key)
        usage["prompt_tokens"] += res.prompt_tokens
        usage["completion_tokens"] += res.completion_tokens
        # 兼容离线 mock：结构化 tool_calls 也转成 Observation 文本回喂（等价 ReAct 步）
        if res.tool_calls:
            messages.append({"role": "assistant", "content": res.content or
                             "\n".join(f"Action: {tc.name}[{', '.join(f'{k}={v}' for k, v in tc.arguments.items())}]"
                                       for tc in res.tool_calls)})
            for tc in res.tool_calls:
                if tc.name in tools.TOOL_FUNCS:
                    result = await asyncio.to_thread(tools.call_tool, tc.name, tc.arguments)
                    results[tc.name] = result
                    obs = json.dumps(tools.compress_tool_result(tc.name, result),
                                     ensure_ascii=False)[:500]
                else:
                    obs = f"未知工具 {tc.name}"
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs})
            continue
        action = parse_action(res.content)
        if action is None:
            fm = _FINAL_RE.search(res.content or "")
            answer = fm.group(1).strip() if fm else (res.content or "").strip()
            return {"success": bool(answer), "answer": answer,
                    "tool_results": results, "usage": usage, "steps": step}
        name, args = action
        messages.append({"role": "assistant", "content": res.content})
        if name not in tools.TOOL_FUNCS:
            observation = f"未知工具 {name}"
        else:
            result = await asyncio.to_thread(tools.call_tool, name, args)
            results[name] = result
            observation = json.dumps(tools.compress_tool_result(name, result),
                                     ensure_ascii=False)[:500]
        messages.append({"role": "user", "content": f"Observation: {observation}"})
    return {"success": False, "answer": "", "tool_results": results,
            "usage": usage, "steps": max_steps}
