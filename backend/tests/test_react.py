"""ReAct 对照实现（Q10）：文本 Action 解析与循环收敛。"""
from __future__ import annotations

from app.services.agent_service.core.react import parse_action, react_run


def test_parse_action_text():
    text = "Thought: 先查天气\nAction: get_weather[city=成都, days=3]"
    name, args = parse_action(text)
    assert name == "get_weather"
    assert args == {"city": "成都", "days": 3}


def test_parse_action_none_when_final():
    assert parse_action("Final Answer: 行程已生成") is None


async def test_react_run_converges_with_mock():
    out = await react_run("我要去成都玩3天，预算2000元")
    assert out["success"] is True
    assert out["steps"] <= 6
    assert "get_weather" in out["tool_results"] or "search_poi" in out["tool_results"]
