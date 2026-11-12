"""AgentCore 节点实现（LangGraph 状态图上的六个节点）。

状态（State）五组字段：
  messages 对话历史 / slots 槽位 / plan_draft 行程草稿 /
  tool_results 工具结果 / revision_count 修订计数

节点：
  intake    意图识别与槽位抽取
  clarify   槽位缺失时逐项反问（绝不让模型脑补）
  plan      基于槽位与 RAG 记忆生成行程骨架与工具查询请求
  tool_call ReAct 式 Function Calling，获取天气、景点、路线、预算事实
  reflect   自检（预算/路线/时间），需要修订则回到 plan（≤3 次）
  respond   流式输出结语
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Callable, Awaitable

from ....common import context
from ....common.config import settings
from ....common.fault import fault
from ....common.logging import get_logger
from ....common.metrics import metrics
from ....common.resilience import TransientError, call_with_resilience
from ....common.tracing import tracer
from ..guard.prompt_guard import prompt_guard
from ..llm.adapter import LLMUpstreamError, estimate_tokens, llm
from ..rag.retriever import retriever
from ...tool_service import tools
from ...tool_service.geo import CITY_ALIAS, CITY_COORDS, city_coords

logger = get_logger("agent.nodes")
Emit = Callable[[str, Any], Awaitable[None]]

_CITIES = tools.list_cities()                 # 有 POI 数据的城市（可规划详细行程）
_CITY_NAMES = list(CITY_COORDS.keys())        # 全部可识别城市（含仅坐标的城市）

_SLOT_PATTERNS = {
    "days": [r"(\d+)\s*天", r"玩\s*(\d+)", r"(\d+)\s*日"],
    "budget": [r"预算\s*(\d+)", r"(\d+)\s*元", r"(\d+)\s*块"],
}
_PREF_KEYWORDS = {
    "亲子": "亲子", "小孩": "亲子", "孩子": "亲子",
    "爬山": "登山", "徒步": "登山",
    "温泉": "温泉", "美食": "美食", "人文": "人文", "历史": "人文",
    "自然": "自然", "风景": "自然", "购物": "购物",
    "穷游": "省钱", "省钱": "省钱", "豪华": "高端",
}
# 目的地启发式：动词 + 2~4 个汉字，用于「去重庆」「到丽江」这类未收录城市
_DEST_VERBS = r"(?:去|到|游|玩|逛|飞|前往|想去|计划去)"
# 非地名停用词：避免把「去机场」「到酒店」这类误当成目的地
_DEST_STOPWORDS = {
    "机场", "车站", "火车站", "高铁站", "酒店", "民宿", "海边", "海岛", "国外",
    "出国", "哪里", "哪儿", "地方", "城市", "附近", "周边", "周末", "假期",
    "公园", "商场", "超市", "医院", "学校", "公司", "家里", "老家", "县城",
}
_REMINDER_INTENT = r"提醒|别忘了|记一下|叫我|闹钟|不用忘"


def _extract_city(text: str) -> str:
    """从自然语言里抽取目的地城市（先精确名，再别名，再动词启发式）。"""
    for name in _CITY_NAMES:
        if name in text:
            return name
    low = text.lower()
    for alias, name in CITY_ALIAS.items():
        if alias in low:
            return name
    m = re.search(_DEST_VERBS + r"\s*([\u4e00-\u9fff]{2,4})", text)
    if m:
        cand = m.group(1)
        for suffix in ("市", "旅行", "旅游", "攻略", "玩", "游"):
            if cand.endswith(suffix) and len(cand) > len(suffix):
                cand = cand[: -len(suffix)]
        if (cand and cand not in _DEST_STOPWORDS
                and not any(w in cand for w in ("怎么", "什么", "多少", "几天", "推荐"))):
            return cand
    return ""


def is_reminder_intent(text: str) -> bool:
    """是否属于「设置提醒」意图（据此走提醒分支而非行程规划）。"""
    if not re.search(_REMINDER_INTENT, text or ""):
        return False
    # 明确在规划行程（含目的地 + 天数/预算/景点）则仍按规划处理
    has_plan = bool(re.search(r"规划|行程|安排|攻略|景点|门票", text or ""))
    return not has_plan


def extract_slots(text: str, base: dict | None = None) -> dict:
    slots = dict(base or {})
    slots.setdefault("destination", "")
    slots.setdefault("days", 0)
    slots.setdefault("budget", 0.0)
    slots.setdefault("preferences", [])
    slots.setdefault("companions", "")
    slots.setdefault("pace", "normal")

    # 目的地：保留已有值，新消息里识别到再覆盖
    found_city = _extract_city(text)
    if found_city:
        slots["destination"] = found_city
    for key, patterns in _SLOT_PATTERNS.items():
        for p in patterns:
            m = re.search(p, text)
            if m:
                slots[key] = float(m.group(1)) if key == "budget" else int(m.group(1))
                break
    prefs = set(slots.get("preferences") or [])
    for kw, tag in _PREF_KEYWORDS.items():
        if kw in text:
            prefs.add(tag)
    if prefs:
        slots["preferences"] = sorted(prefs)
    if re.search(r"带(小孩|孩子|娃)", text):
        slots["companions"] = "亲子"
    elif re.search(r"带(老人|父母|父母亲|长辈)", text):
        slots["companions"] = "老人"
    elif re.search(r"情侣|蜜月", text):
        slots["companions"] = "情侣"
    if re.search(r"轻松|慢节奏|休闲", text):
        slots["pace"] = "relaxed"
    elif re.search(r"紧凑|多去几个|玩满", text):
        slots["pace"] = "tight"
    return slots


# ─────────────────────── 节点 ───────────────────────

async def intake(state: dict, emit: Emit) -> dict:
    """>>> 意图识别与槽位抽取<<<"""
    with tracer.span("node.intake"):
        last = state.get("messages", [])[-1]["content"] if state.get("messages") else ""
        slots = extract_slots(last, state.get("slots"))
        await emit("token", {"text": "正在理解你的旅行需求…\n"})
        state["slots"] = slots
        return {"slots": slots}


async def clarify(state: dict, emit: Emit) -> dict:
    """>>> 槽位缺失时逐项反问（有密钥时由模型生成自然话术）<<<"""
    slots = state.get("slots", {})
    missing = []
    if not slots.get("destination"):
        missing.append("想去的目的地城市")
    if not slots.get("days"):
        missing.append("计划玩几天")
    if not slots.get("budget"):
        missing.append("预算大概多少")

    fallback = "为了给你规划行程，我还需要知道：" + "；".join(missing) + "。"
    last = state.get("messages", [])[-1]["content"] if state.get("messages") else ""
    q = ""
    # 有密钥时让模型生成自然追问；离线则用本地模板，保证可用
    from ....common.runtime_config import runtime_config
    cfg = await runtime_config.get_llm()
    if (state.get("llm_api_key") or cfg.get("api_key") or "").strip():
        try:
            res = await llm.chat([
                {"role": "system", "content":
                    "你是中文旅行规划助手。用户的需求还缺关键信息，请用亲切自然的一句话"
                    "追问缺失项，不要罗列清单，不要编造行程。"},
                {"role": "user", "content":
                    f"用户说：{last}\n目前已知：目的地={slots.get('destination') or '未定'}、"
                    f"天数={slots.get('days') or '未定'}、预算={slots.get('budget') or '未定'}。"
                    f"还缺：{'、'.join(missing)}。"},
            ], model=state.get("model"), api_key=state.get("llm_api_key"))
            q = (res.content or "").strip()
        except Exception as exc:      # 模型不可用则退回模板，不阻塞
            logger.warning("clarify 模型生成失败，用模板兜底: %s", exc)
    if not q:
        q = fallback
    await emit("token", {"text": q + "\n"})
    return {"assistant_message": q}


async def reminder(state: dict, emit: Emit) -> dict:
    """>>> 设置未来行程提醒（不生成行程，直接调用 set_reminder 工具）<<<"""
    last = state.get("messages", [])[-1]["content"] if state.get("messages") else ""
    await emit("token", {"text": "好的，我来帮你设置提醒。\n"})
    args = {"title": _reminder_title(last), "when": last, "detail": last[:120]}
    await emit("tool_call", {"tool": "set_reminder", "arguments": args})
    meta: dict = {}
    result = await _run_tool("set_reminder", args, meta)
    await emit("tool_result", {"tool": "set_reminder",
                               "summary": _summarize("set_reminder", result),
                               "source": meta.get("source", "native")})
    results = {**state.get("tool_results", {}), "set_reminder": result}
    if result.get("error"):
        msg = f"提醒设置失败：{result['error']}"
    else:
        msg = result.get("hint") or f"已设置提醒：{result.get('remind_at', '')}"
    await emit("token", {"text": msg + "\n"})
    return {"tool_results": results, "assistant_message": msg}


def _reminder_title(text: str) -> str:
    """从原话里截取提醒事项作为标题。"""
    t = re.sub(r"^(帮我|请|麻烦)?\s*", "", (text or "").strip())
    t = re.sub(r"提醒我|提醒|别忘了|记一下|叫我", "", t).strip("，,。. ")
    return (t or "行程提醒")[:60]


async def plan(state: dict, emit: Emit) -> dict:
    """>>> 基于槽位与 RAG 生成行程骨架与工具查询请求 <<<"""
    with tracer.span("node.plan"):
        slots = state.get("slots", {})
        city = slots.get("destination", "")
        revise = state.get("revision_count", 0) > 0
        hint = "（根据你的反馈重新调整中…）" if revise else ""
        await emit("token", {"text": f"好的，正在为你规划{city}的行程{hint}\n"})

        # RAG：检索攻略知识（静态知识走 RAG，实时事实走工具）
        citations = []
        try:
            query = f"{city} {' '.join(slots.get('preferences', []))} 攻略 门票 开放时间"
            citations = await retriever.retrieve(query, city=city or None)
        except Exception as exc:  # RAG 失败不阻塞主流程
            logger.warning("RAG 检索失败，跳过", extra={"event": "rag_failed"})

        requests = {
            "city": city,
            "days": int(slots.get("days") or 3),
            "budget": float(slots.get("budget") or 0),
            "preferences": slots.get("preferences", []),
            "budget_style": state.get("budget_style", "comfort"),
        }
        state["plan_requests"] = requests
        state["citations"] = citations
        return {"plan_requests": requests, "citations": citations}


def _build_reference_block(citations: list[dict], budget_tokens: int = 2000) -> str:
    """把 RAG 检索块拼成「参考资料」注入 Prompt（Q21）。

    - 按相似度从高到低排序，累计超过预算 token 即截断；
    - 保留块编号 [1][2]…，前端可据此展示引用来源；
    - 与 system prompt 隔离，本身也是 prompt 防护的一部分。
    """
    if not citations:
        return ""
    ordered = sorted(citations, key=lambda c: -c.get("score", 0))
    parts: list[str] = []
    used = 0
    for i, c in enumerate(ordered, start=1):
        line = f"[{i}] {c.get('title', '')}：{c.get('text', '')}"
        cost = estimate_tokens(line)
        if used + cost > budget_tokens:
            break
        parts.append(line)
        used += cost
    if not parts:
        return ""
    return ("参考资料（来自知识库，优先据此回答；资料没有的用工具结果；"
            "都没有就明确说不知道，不要编造）：\n" + "\n".join(parts))


async def tool_call(state: dict, emit: Emit) -> dict:
    """>>> Function Calling 循环：获取天气 / 景点 / 路线 / 预算事实 <<<"""
    req = state.get("plan_requests", {})
    results: dict[str, Any] = {}
    usage = state.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0})

    # RAG 检索结果注入（幻觉治理核心：让模型「有据可依」）
    reference = _build_reference_block(state.get("citations", []))
    last_user = state.get("messages", [])[-1]["content"] if state.get("messages") else ""
    # 带上用户原话：模型才能理解「提醒」「带娃」等意图与细节
    user_content = (
        f"目的地：{req.get('city')}；天数：{req.get('days')}天；预算：{req.get('budget')}元；"
        f"偏好：{'、'.join(req.get('preferences') or []) or '无'}\n用户原话：{last_user}"
    )
    if reference:
        user_content += "\n\n" + reference

    messages = [
        {"role": "system", "content":
            "你是专业的中文旅行规划助手。请严格依据工具返回的真实数据与参考资料规划行程，"
            "不要编造开放时间、票价、政策；资料没有的信息请明确说不知道，"
            "并提示以景区当日实际为准。"},
    ]
    # 长期记忆：稳定偏好自动注入 system prompt（Q12）
    prefs = state.get("prefs") or {}
    if prefs:
        from ..memory.long_term import describe_preferences
        messages.append({"role": "system",
                         "content": f"用户长期偏好：{describe_preferences(prefs)}。请优先满足。"})
    # 短期记忆：滑动窗口 + 摘要（Q12）——最近 N 轮原文，更早历史压缩为摘要
    from ..memory.short_term import session_memory
    history_ctx = session_memory.build_context(state)
    messages.extend(history_ctx[:-1] if len(history_ctx) > 1 else [])
    messages.append({"role": "user", "content": prompt_guard.wrap_user_content(user_content)})

    # 工具白名单：用户在输入框左下角选择「完全访问 / 仅天气 / 仅景点 …」
    enabled = state.get("tools_enabled")
    tool_schemas = tools.TOOL_SCHEMAS
    if enabled:
        allowed = {str(n) for n in enabled}
        tool_schemas = [s for s in tools.TOOL_SCHEMAS
                        if s.get("function", {}).get("name") in allowed]
        if not tool_schemas:           # 白名单没命中任何工具 → 退回全部，避免空转
            tool_schemas = tools.TOOL_SCHEMAS

    async def _llm_call():
        if fault.model_down:      # 故障演练：让失败经由熔断器统计
            raise TransientError("模拟大模型不可用")
        try:
            return await llm.chat(messages, tools=tool_schemas,
                                  model=state.get("model"),
                                  api_key=state.get("llm_api_key"),
                                  images=state.get("images"))
        except LLMUpstreamError as exc:
            # 上游可重试错误（429/5xx/超时）交给韧性链路重试；
            # 鉴权/余额/模型类错误立即抛出，由上层如实告知用户
            if exc.retryable:
                raise TransientError(exc.message) from exc
            logger.error("模型调用失败", extra={"event": "llm_error", "tool": exc.message})
            raise

    final_text = ""
    max_loops = 6
    arg_retry = 0          # 参数校验失败回喂重生成计数（Q9：最多 2 次）
    for _ in range(max_loops):
        # 不提供 fallback：失败会经熔断统计后抛出，由上层统一降级
        llm_res = await call_with_resilience(
            _llm_call,
            downstream=f"llm:{llm.provider}",
            timeout=settings.llm_timeout_seconds,
        )
        usage["prompt_tokens"] += llm_res.prompt_tokens
        usage["completion_tokens"] += llm_res.completion_tokens
        if llm_res.model:
            state["model_used"] = llm_res.model
        if llm_res.provider:
            state["provider_used"] = llm_res.provider

        if not llm_res.tool_calls:
            final_text = llm_res.content
            break

        # 参数二次校验（Pydantic）：不合法则把错误回喂模型重新生成，最多 2 次
        valid_calls: list = []
        errors: list[str] = []
        _fill_from_slots(llm_res.tool_calls, req)
        for tc in llm_res.tool_calls:
            fixed, err = tools.validate_tool_args(tc.name, tc.arguments)
            if err is None and fixed is not None:
                tc.arguments = fixed
                valid_calls.append(tc)
            else:
                errors.append(f"{tc.name}: {err}")
        if errors and arg_retry < 2:
            arg_retry += 1
            messages.append({"role": "assistant", "content": llm_res.content})
            messages.append({"role": "user",
                             "content": "工具参数校验失败：" + "；".join(errors)
                                        + "。请修正参数后重新调用工具。"})
            await emit("token", {"text": f"参数校验未通过（{errors[0]}），重新生成…\n"})
            continue
        if errors and not valid_calls:
            # 仍失败 → 降级：向用户反问而非硬执行
            q = "我需要确认一下：" + "；".join(errors) + "。请补充正确的信息。"
            await emit("token", {"text": q})
            return {"assistant_message": q, "tool_results": results,
                    "token_usage": usage}

        messages.append({
            "role": "assistant",
            "content": llm_res.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                for tc in valid_calls
            ],
        })
        for tc in valid_calls:
            await emit("tool_call", {"tool": tc.name, "arguments": tc.arguments})
            meta: dict = {}
            result = await _run_tool(tc.name, tc.arguments, meta)
            results[tc.name] = result
            await emit("tool_result", {"tool": tc.name, "summary": _summarize(tc.name, result),
                                       "source": meta.get("source", "native")})
            # 返回值先压缩再回喂模型，只保留必要字段，省 token（Q9）
            compressed = tools.compress_tool_result(tc.name, result)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(compressed, ensure_ascii=False)})

    state["token_usage"] = usage
    metrics.add_tokens(usage["prompt_tokens"] + usage["completion_tokens"])
    return {"tool_results": results, "token_usage": usage,
            "assistant_message": final_text}


def _fill_from_slots(tool_calls: list, req: dict) -> None:
    """把已知槽位补进工具参数，避免模型漏填关键字段导致校验失败。

    例如模型只给了 get_weather 的 days，city 为空 → 用本次规划的目的地补齐。
    """
    city = str(req.get("city") or "")
    days = int(req.get("days") or 3)
    budget = float(req.get("budget") or 0)
    for tc in tool_calls:
        args = tc.arguments if isinstance(tc.arguments, dict) else {}
        if "city" in args or tc.name in ("get_weather", "search_poi", "estimate_budget"):
            if not args.get("city") and city:
                args["city"] = city
        if tc.name == "get_weather" and not args.get("days"):
            args["days"] = days
        if tc.name == "estimate_budget":
            if not args.get("days"):
                args["days"] = days
            if args.get("budget") in (None, ""):
                args["budget"] = budget
        tc.arguments = args


# 可经 MCP 子进程执行的工具（不可用时自动回落原生实现）
_MCP_TOOLS = {
    "get_weather", "search_poi", "geocode", "reverse_geocode", "plan_route",
    "estimate_budget", "get_current_time", "set_reminder",
    "search_knowledge", "notify_desktop",
}


async def _call_via_mcp(name: str, arguments: dict) -> dict:
    """通过 MCP 协议调用子进程中的工具；用户身份在调用前注入参数。"""
    from ...mcp_service.manager import McpUnavailable, mcp_manager
    if not mcp_manager.enabled:
        raise McpUnavailable("MCP 未就绪")
    args = dict(arguments or {})
    if name in ("set_reminder", "notify_desktop"):
        args["user_id"] = context.get_user_id() or 0
    return await mcp_manager.call_for(name, args)


async def _run_tool(name: str, arguments: dict, meta: dict | None = None) -> dict:
    """工具调用统一走 超时 → 重试 → 熔断 → 兜底 链路；工具故障不阻塞主流程。

    - 优先经 MCP 子进程执行（MCP 未就绪 / 传输失败则回落原生实现）；
    - 天气走 cache-aside 缓存（Q38）：TTL 1 小时+抖动、空值防穿透、互斥防击穿。
    - meta 回填本次实际执行来源（mcp / native），用于前端标识。
    """
    if meta is not None:
        meta.setdefault("source", "native")

    async def _call():
        if name in fault.tool_down:
            raise TransientError(f"模拟工具 {name} 宕机")
        # ① MCP 优先
        if name in _MCP_TOOLS:
            try:
                result = await _call_via_mcp(name, arguments)
                if meta is not None:
                    meta["source"] = "mcp"
                return result
            except Exception as exc:                 # 含 McpUnavailable，一并回落
                if meta is not None:
                    meta["source"] = "native"
                logger.warning("工具 %s 走 MCP 失败，回落原生实现: %s", name, exc)
        # ② 原生实现（原有链路）
        if name == "set_reminder":
            # 行程提醒需要落库，走异步写（用户身份取自协程上下文）
            from ..reminders import create_reminder
            return await create_reminder(
                user_id=context.get_user_id(),
                title=str(arguments.get("title") or "行程提醒"),
                when=str(arguments.get("when") or ""),
                detail=str(arguments.get("detail") or ""))
        if name == "search_knowledge":
            q = str(arguments.get("query") or "")
            hits = await retriever.retrieve(q, city=str(arguments.get("city") or "") or None,
                                            topk=int(arguments.get("topk") or 5))
            return {"query": q, "backend": retriever.backend,
                    "chunks": retriever.chunk_count, "items": hits}
        if name == "notify_desktop":
            from ...mcp_service.desktop import show_toast
            from ...db.models import Notification
            from ...db.session import SessionLocal
            uid = context.get_user_id()
            if not uid:
                return {"error": "无法确定用户身份，未能推送通知"}
            title = str(arguments.get("title") or "行程提醒")
            content = str(arguments.get("content") or "")
            async with SessionLocal() as db:
                db.add(Notification(user_id=uid, kind="reminder", title=title[:200],
                                    content=content[:500],
                                    link=str(arguments.get("link") or "")[:255]))
                await db.commit()
            shown = show_toast(title, content)
            return {"title": title, "desktop_shown": shown, "hint": f"已提醒：{title}"}
        if name == "get_weather":
            from ....common.cache import cached_get_or_build
            city = str(arguments.get("city") or "")
            days = int(arguments.get("days") or 3)
            cached = await cached_get_or_build(
                f"cache:weather:{city}:{days}",
                lambda: asyncio.to_thread(tools.get_weather, city, days),
                ttl=3600)
            if cached is not None:
                return cached
            # 缓存空值（上游无数据）→ 直接走 mock 兜底
            return await asyncio.to_thread(tools.get_weather, city, days)
        # 工具内部可能包含真实网络请求，放入线程池避免阻塞事件循环
        return await asyncio.to_thread(tools.call_tool, name, arguments)

    async def _fallback():
        return {"error": f"{name} 暂时不可用", "degraded": True}

    return await call_with_resilience(
        _call, downstream=f"tool:{name}", timeout=8.0, fallback=_fallback,
    )


def _summarize(name: str, result: dict) -> str:
    if name == "get_weather" and result.get("forecast"):
        f = result["forecast"][0]
        return f"{f['condition']} {f['low']}~{f['high']}℃"
    if name == "search_poi":
        return f"命中 {len(result.get('items', []))} 个景点"
    if name == "estimate_budget":
        return f"预计总花费 ¥{result.get('total', 0)}"
    if name == "plan_route":
        return f"{result.get('transport')} {result.get('duration_min')}分钟 ¥{result.get('cost')}"
    if name == "set_reminder":
        return result.get("hint") or f"提醒时间 {result.get('remind_at', '')}"
    if name == "get_current_time":
        return f"{result.get('date')} {result.get('time')} {result.get('weekday', '')}"
    if name == "geocode":
        return f"{result.get('name')} ({result.get('source')})" if result.get("found") \
            else "未找到该地点"
    if name == "reverse_geocode":
        return f"定位到 {result.get('name')}" if result.get("found") else "仅得到经纬度"
    if name == "search_knowledge":
        return f"召回 {len(result.get('items', []))} 条（{result.get('backend', '')}）"
    if name == "notify_desktop":
        return result.get("hint") or "已推送桌面通知"
    return "完成"


_GENERIC_POI_TEMPLATES = [
    ("市中心地标", "sightseeing", 0.0, 120, "城市标志性景点，适合首日打卡"),
    ("本地博物馆", "culture", 40.0, 120, "了解当地历史与人文脉络"),
    ("老城步行街", "shopping", 0.0, 90, "品尝当地小吃、挑选伴手礼"),
    ("城市公园", "nature", 0.0, 90, "休闲散步，感受当地生活节奏"),
    ("特色观景台", "sightseeing", 60.0, 90, "俯瞰城市全景，适合拍照留念"),
    ("周边古镇", "culture", 50.0, 180, "半日往返的传统街区与民俗体验"),
]


def _generic_pois(city: str, days: int) -> list[dict]:
    """无 POI 数据城市的通用景点骨架（保证行程结构完整，不出现空白天）。"""
    city_name = city or "目的地"
    need = max(days * 2, 6)
    out: list[dict] = []
    for i in range(need):
        name, category, ticket, duration, note = _GENERIC_POI_TEMPLATES[i % len(_GENERIC_POI_TEMPLATES)]
        out.append({
            "name": f"{city_name}{name}",
            "category": category,
            "ticket": ticket,
            "duration_min": duration,
            "note": note,
            "rating": round(4.5 - (i % 5) * 0.1, 1),
            "tags": [],
            "lat": None,
            "lon": None,
        })
    return out


def assemble_draft(state: dict, cheap: bool = False) -> dict:
    """由工具事实组装结构化行程草稿（reflect 阶段调用）。"""
    slots = state.get("slots", {})
    req = state.get("plan_requests", {})
    tr = state.get("tool_results", {})
    city = slots.get("destination", "")
    days = int(slots.get("days") or 3)
    budget = float(slots.get("budget") or 0)
    avoid_hiking = "登山" in (slots.get("preferences") or [])
    family = slots.get("companions") == "亲子"

    pois = (tr.get("search_poi") or {}).get("items", [])
    # 兜底①：模型没调工具 / 工具结果为空时，直接用城市再检索一次
    if not pois and city:
        try:
            pois = (tools.search_poi(city, topk=12) or {}).get("items", [])
        except Exception:
            pois = []
    # 兜底②：该城市暂无 POI 数据时，用通用景点骨架填充，
    # 保证「有效信息进入行程」，避免每天空白、保存后详情页几乎无内容
    if not pois:
        pois = _generic_pois(city, days)
    # 偏好与约束过滤
    filtered = []
    for p in pois:
        if avoid_hiking and p.get("category") == "nature" and "登山" in p.get("tags", []):
            continue
        if cheap and p.get("ticket", 0) > 60:
            continue
        filtered.append(p)
    if not filtered:
        filtered = pois
    if family:
        filtered.sort(key=lambda x: (0 if "亲子" in x.get("tags", []) else 1, -x.get("rating", 0)))
    filtered.sort(key=lambda x: -x.get("rating", 0))

    weather = (tr.get("get_weather") or {}).get("forecast", [])
    per_day = 3 if slots.get("pace") == "tight" else 2
    day_list = []
    idx = 0
    for d in range(days):
        items = []
        for slot_name in (["morning", "afternoon", "evening"][:per_day]):
            if idx >= len(filtered):
                break
            p = filtered[idx]
            idx += 1
            items.append({
                "time_slot": slot_name,
                "poi_name": p["name"],
                "category": p.get("category", "sightseeing"),
                "cost": float(p.get("ticket", 0)),
                "duration_min": int(p.get("duration_min", 120)),
                "note": p.get("note", ""),
                "lat": p.get("lat"),
                "lon": p.get("lon"),
            })
        w = weather[d] if d < len(weather) else {}
        day_list.append({
            "day_no": d + 1,
            "city": city,
            "weather": f"{w.get('condition', '')} {w.get('low', '')}~{w.get('high', '')}℃" if w else "",
            "items": items,
            "day_cost": round(sum(i["cost"] for i in items), 1),
        })

    budget_est = tr.get("estimate_budget") or {}
    if cheap:
        budget_est = tools.estimate_budget(city=city, days=days, budget=budget,
                                           travel_style="budget")
    ticket_total = sum(i["cost"] for d in day_list for i in d["items"])
    total = float(budget_est.get("total", ticket_total))
    over = max(0.0, total - budget) if budget else 0.0

    draft = {
        "title": f"{city}{days}日行程",
        "destination": city,
        "days": days,
        "budget": budget,
        "total_cost": round(total, 1),
        "within_budget": over <= 0,
        "over_budget": round(over, 1),
        "ticket_total": round(ticket_total, 1),
        "breakdown": budget_est.get("breakdown", {}),
        "day_list": day_list,
        "citations": state.get("citations", []),
        "warnings": [],
        "center": (lambda c: {"lat": c[0], "lon": c[1]} if c else None)(city_coords(city)),
    }
    return draft


async def reflect(state: dict, emit: Emit) -> dict:
    """>>> 自检：预算是否超支、路线顺序是否合理、时间是否冲突 <<<"""
    with tracer.span("node.reflect"):
        revise = state.get("revision_count", 0)
        cheap = revise > 0
        draft = assemble_draft(state, cheap=cheap)
        warnings: list[str] = []

        # ① 预算自检
        if not draft["within_budget"]:
            warnings.append(f"预算超出约 {draft['over_budget']} 元")
        # ② 路线顺序自检（同日景点不重复）
        for d in draft["day_list"]:
            names = [i["poi_name"] for i in d["items"]]
            if len(names) != len(set(names)):
                warnings.append(f"第 {d['day_no']} 天景点重复")
        # ③ 时间冲突自检（单日总时长）
        for d in draft["day_list"]:
            total_min = sum(i["duration_min"] for i in d["items"])
            if total_min > 10 * 60:
                warnings.append(f"第 {d['day_no']} 天行程过满（{total_min // 60} 小时）")
        draft["warnings"] = warnings

        await emit("plan_update", draft)

        need_revise = bool([w for w in warnings if "预算超出" in w]) and \
            revise < settings.revision_max
        if need_revise:
            state["plan_draft"] = draft
            state["revision_count"] = revise + 1
            state["budget_style"] = "budget"
            await emit("token", {
                "text": f"发现{warnings[0]}，我调整一下住宿档位与景点选择…\n"})
            state["_revise"] = True
            return {"plan_draft": draft, "revision_count": revise + 1,
                    "budget_style": "budget", "_revise": True}
        if warnings:
            await emit("token", {"text": "提示：" + "；".join(warnings) + "。\n"})
        state["_revise"] = False
        state["plan_draft"] = draft
        return {"plan_draft": draft, "_revise": False}


async def respond(state: dict, emit: Emit) -> dict:
    """>>> 流式输出结语 <<<"""
    text = state.get("assistant_message") or "行程已生成，请在右侧查看。"
    if not prompt_guard.is_in_scope(text):
        text = "抱歉，我只能协助旅行规划相关的问题。"
    # 以最终草稿为准追加权威结论，避免正文数字与右侧预览不一致
    draft = state.get("plan_draft") or {}
    if draft.get("total_cost") is not None:
        total = float(draft.get("total_cost") or 0)
        budget = float(draft.get("budget") or 0)
        if budget:
            verdict = ("在预算范围内" if draft.get("within_budget")
                       else f"超出预算约 {float(draft.get('over_budget') or 0):.0f} 元")
            text += f"\n最终方案：预计总花费 ¥{total:.0f}（预算 ¥{budget:.0f}，{verdict}）。"
        else:
            text += f"\n最终方案：预计总花费 ¥{total:.0f}。"
    # 打字机效果：逐段流式推送
    step = 12
    for i in range(0, len(text), step):
        await emit("token", {"text": text[i:i + step]})
    return {}
