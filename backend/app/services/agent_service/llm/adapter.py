"""模型层：统一适配器 `chat(messages, tools)`。

- mock：离线确定性实现，按「已收集到的工具结果」决定下一步调用哪些工具，
  再给出总结文本 —— 真实地把 Function Calling 循环、工具注册表、熔断与重试
  跑通，不依赖外网与 API Key，答辩现场稳定可演示。
- openai：调用真实 OpenAI 兼容接口（DeepSeek / 通义千问等），走 httpx。
切换模型只改配置，不动业务代码。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from ....common.config import settings
from ....common.logging import get_logger

logger = get_logger("llm")


class LLMUpstreamError(Exception):
    """上游大模型返回的可读错误（鉴权失败 / 余额不足 / 模型不存在 / 限流等）。"""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.status = status
        self.retryable = retryable


def _readable_upstream_error(status: int, body: str) -> LLMUpstreamError:
    """把上游 HTTP 错误翻译成用户能看懂的中文提示。"""
    snippet = (body or "").strip().replace("\n", " ")[:180]
    if status == 401:
        return LLMUpstreamError(
            "API Key 无效或已失效（401），请在个人中心重新填写正确的 DeepSeek 密钥。",
            status=status)
    if status == 402:
        return LLMUpstreamError(
            "DeepSeek 账户余额不足（402），请充值后再试。", status=status)
    if status == 403:
        return LLMUpstreamError(f"该密钥无权访问此模型（403）。{snippet}", status=status)
    if status == 429:
        return LLMUpstreamError(
            "上游限流（429），请求过于频繁，请稍后重试。", status=status, retryable=True)
    if status >= 500:
        return LLMUpstreamError(
            f"上游服务异常（{status}），请稍后重试。{snippet}", status=status, retryable=True)
    return LLMUpstreamError(f"上游返回错误（{status}）：{snippet or '无详细信息'}",
                            status=status)


def _is_model_missing(status: int, body: str) -> bool:
    """判断是否属于「模型不存在/不可用」，可用于自动切换候选模型。"""
    if status not in (400, 404):
        return False
    low = (body or "").lower()
    return ("model" in low and any(
        k in low for k in ("not exist", "not found", "does not exist", "invalid",
                           "unsupported", "unknown"))) or "model_not_found" in low


def _looks_like_vision_reject(body: str) -> bool:
    """上游 400 是否属于「不支持图片/多模态输入」（用于纯文本降级重试）。"""
    low = (body or "").lower()
    return any(k in low for k in ("image", "vision", "multimodal", "modalit"))


def _with_images(messages: list[dict], images: list[str] | None) -> list[dict]:
    """把图片（data URL）以 OpenAI 兼容多模态格式挂到最后一条用户消息上。

    模型由此真正「看到」图片内容，而不是只看到 /api/media/xx 的路径文字。
    """
    if not images:
        return messages
    msgs = list(messages)
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            parts: list[dict] = [{"type": "text", "text": m["content"]}]
            parts += [{"type": "image_url", "image_url": {"url": u}} for u in images]
            msgs[i] = {**m, "content": parts}
            break
    return msgs


# 记住每个 (base_url, 展示模型) 实测可用的真实上游模型名
_WORKING_MODEL: dict[tuple[str, str], str] = {}


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    provider: str = ""          # "openai"=真实上游调用 / "mock"=离线模拟（用于前端标识）

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文按 1 字≈1token，英文按 4 字符≈1token。"""
    if not text:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = len(text) - cjk
    return cjk + max(1, other // 4)


def _extract(patterns: list[str], text: str, default: str = "") -> str:
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return default


class LLMAdapter:
    """统一适配器：provider/model/api_key 均可在运行时由管理员配置。"""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.llm_provider

    async def _runtime(self) -> dict:
        from ....common.runtime_config import runtime_config
        return await runtime_config.get_llm()

    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   model: str | None = None, api_key: str | None = None,
                   images: list[str] | None = None) -> LLMResult:
        cfg = await self._runtime()
        # 优先使用用户自己的 Key，其次管理员全局 Key；两者都没有则离线模拟
        key = (api_key or cfg.get("api_key") or "").strip()
        chosen = model or cfg.get("default_model") or "deepseek-v4-flash"
        if key:
            return await self._openai_chat(messages, tools, chosen,
                                           {**cfg, "api_key": key}, images=images)
        return self._mock_chat(messages, tools, chosen)

    # ─────────────────── mock 实现 ───────────────────
    def _mock_chat(self, messages: list[dict], tools: list[dict] | None,
                   model: str | None = None) -> LLMResult:
        last_user = next((m["content"] for m in reversed(messages)
                          if m.get("role") == "user"), "")
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        prompt_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
        # 尊重前端选定的工具白名单（完全访问时即为全部工具）
        allowed = {s.get("function", {}).get("name") for s in (tools or [])} or None

        def _ok(name: str) -> bool:
            return allowed is None or name in allowed

        city = _extract([r"目的地[:：]\s*([^\s；;，,]+)"], last_user, "") \
            or _extract([r"(成都|北京|上海|杭州|西安|厦门)"], last_user, "")
        days = _extract([r"天数[:：]\s*(\d+)", r"(\d+)\s*天"], last_user, "")
        days = int(days) if days.isdigit() else 0
        budget = _extract([r"预算\s*([\d.]+)", r"([\d.]+)\s*元"], last_user, "")
        budget = float(budget) if budget else 0.0

        # 提醒意图：离线也能演示「提前设置未来行程提醒」工具
        if len(tool_msgs) == 0 and re.search(r"提醒|别忘了|记一下|叫我", last_user) \
                and _ok("set_reminder"):
            when = last_user
            tm = re.search(r"(明天|后天|\d+\s*天后|早上|上午|中午|下午|晚上|\d+\s*[:：点])", last_user)
            if tm:
                when = tm.group(0)
            return LLMResult(tool_calls=[ToolCall("c0", "set_reminder", {
                "title": "行程提醒", "when": when, "detail": last_user[:80]})],
                prompt_tokens=prompt_tokens, completion_tokens=20,
                model="mock-llm", provider="mock")

        # 第一轮：还没有工具结果 → 查天气 + 搜景点
        if len(tool_msgs) == 0:
            calls = [ToolCall("c1", "get_weather", {"city": city, "days": days or 3}),
                     ToolCall("c2", "search_poi", {"city": city, "topk": 12})]
            calls = [c for c in calls if _ok(c.name)]
            if not calls:                 # 白名单里只有预算/路线等 → 直接进第二轮
                calls = [ToolCall("c3", "estimate_budget",
                                  {"city": city, "days": days or 3, "budget": budget})] \
                    if _ok("estimate_budget") else []
            return LLMResult(tool_calls=calls, prompt_tokens=prompt_tokens,
                             completion_tokens=40, model="mock-llm", provider="mock")

        # 第二轮：已有景点结果 → 估预算 + 算路线
        if len(tool_msgs) <= 2:
            poi_names = self._poi_names_from(tool_msgs)
            calls = []
            if _ok("estimate_budget"):
                calls.append(ToolCall("c3", "estimate_budget",
                                      {"city": city, "days": days or 3, "budget": budget}))
            if _ok("plan_route") and len(poi_names) >= 2:
                calls.append(ToolCall("c4", "plan_route",
                                      {"from_poi": poi_names[0], "to_poi": poi_names[1],
                                       "city": city}))
            if calls:
                return LLMResult(tool_calls=calls, prompt_tokens=prompt_tokens,
                                 completion_tokens=30, model="mock-llm", provider="mock")

        # 第三轮：信息齐备 → 产出总结文本
        content = self._compose_summary(last_user, tool_msgs, city, days, budget)
        return LLMResult(content=content, prompt_tokens=prompt_tokens,
                         completion_tokens=estimate_tokens(content),
                         model="mock-llm", provider="mock")

    def _poi_names_from(self, tool_msgs: list[dict]) -> list[str]:
        for m in tool_msgs:
            try:
                data = json.loads(m.get("content", "{}"))
            except Exception:
                continue
            if isinstance(data, dict) and data.get("items"):
                return [i.get("name", "") for i in data["items"] if i.get("name")]
        return []

    def _compose_summary(self, message: str, tool_msgs: list[dict],
                         city: str, days: int, budget: float) -> str:
        weather = ""
        pois: list[str] = []
        total = 0.0
        for m in tool_msgs:
            try:
                data = json.loads(m.get("content", "{}"))
            except Exception:
                continue
            if isinstance(data, dict):
                if data.get("forecast"):
                    f0 = data["forecast"][0]
                    weather = f"{f0['date']} {f0['condition']} {f0['low']}~{f0['high']}℃"
                if data.get("items") and not pois:
                    pois = [i["name"] for i in data["items"][:6]]
                if "total" in data:
                    total = data.get("total", 0.0)
        parts = [f"好的，我来为你规划{city or '目的地'}{days or ''}天的行程。"]
        if weather:
            parts.append(f"未来天气：{weather}，{('适合出行' if '雨' not in weather else '记得带伞')}。")
        if pois:
            parts.append(f"我为你挑选了 {len(pois)} 个景点，包括{'、'.join(pois[:4])}等，"
                         f"已按地理位置与时间顺序排入每天的行程。")
        if total:
            over = total - budget if budget else 0
            tip = (f"预计总花费约 {total:.0f} 元，超出预算 {over:.0f} 元，建议下调住宿档位或替换付费景点。"
                   if budget and over > 0 else
                   f"预计总花费约 {total:.0f} 元，在预算范围内。")
            parts.append(tip)
        # 引用标注：参考资料块编号 [1][2]…（幻觉治理：让依据可溯源）
        refs = re.findall(r"\[(\d+)\]", message or "")
        if refs:
            uniq = sorted({int(r) for r in refs})
            parts.append("以上安排参考了知识库资料 " + "、".join(f"[{n}]" for n in uniq) + "。")
        parts.append("具体开放时间与票价请以景区当日实际为准。")
        parts.append("你可以在右侧查看分日行程，告诉我「第二天换个便宜点的」或「加个温泉」，我会继续调整。")
        return "".join(parts)

    # ─────────────────── openai / deepseek 实现 ───────────────────
    async def _openai_chat(self, messages: list[dict], tools: list[dict] | None,
                           model: str | None, cfg: dict,
                           images: list[str] | None = None) -> LLMResult:
        base_url = (cfg.get("base_url") or settings.llm_base_url).rstrip("/")
        api_key = cfg.get("api_key") or settings.llm_api_key
        temperature = cfg.get("temperature", settings.llm_temperature)
        max_tokens = cfg.get("max_tokens", settings.llm_max_tokens)

        # 展示用模型 id → 真实上游模型名尝试链（应对「模型不存在」）
        from ....common.runtime_config import resolve_model_chain
        chain = resolve_model_chain(cfg, model)
        cache_key = (base_url, model or "")
        cached = _WORKING_MODEL.get(cache_key)
        if cached and cached in chain:
            chain = [cached, *[m for m in chain if m != cached]]

        last_error: LLMUpstreamError | None = None
        # 上传图片以多模态 image_url 形式随最后一条用户消息发送（模型据此看图分析）
        send_messages = _with_images(messages, images)
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            for api_model in chain:
                payload: dict[str, Any] = {
                    "model": api_model,
                    "messages": send_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"
                headers = {"Authorization": f"Bearer {api_key}",
                           "Content-Type": "application/json"}
                try:
                    resp = await client.post(f"{base_url}/chat/completions",
                                             headers=headers, json=payload)
                except httpx.TimeoutException as exc:
                    raise LLMUpstreamError(
                        f"调用模型超时（{settings.llm_timeout_seconds:.0f}s），请检查网络后重试。",
                        retryable=True) from exc
                except httpx.HTTPError as exc:
                    raise LLMUpstreamError(f"无法连接模型服务：{exc}", retryable=True) from exc

                if (resp.status_code == 400 and send_messages is not messages
                        and _looks_like_vision_reject(resp.text)):
                    # 所选模型不支持图片输入 → 纯文本重试一次（图片引用仍在文本里，功能不中断）
                    logger.warning("上游模型不支持图片输入，已回退纯文本重试",
                                   extra={"tool": f"model={api_model}"})
                    payload["messages"] = messages
                    resp = await client.post(f"{base_url}/chat/completions",
                                             headers=headers, json=payload)

                if resp.status_code >= 400:
                    body = resp.text
                    if api_model != chain[-1] and _is_model_missing(resp.status_code, body):
                        logger.warning(
                            "上游不支持该模型，自动切换候选",
                            extra={"tool": f"model={api_model}"})
                        last_error = _readable_upstream_error(resp.status_code, body)
                        continue          # 试下一个候选模型
                    err = _readable_upstream_error(resp.status_code, body)
                    logger.error("上游模型调用失败", extra={"tool": f"{resp.status_code} {api_model}"})
                    raise err

                data = resp.json()
                _WORKING_MODEL[cache_key] = api_model       # 记住可用模型
                if api_model != chain[0]:
                    logger.info("已自动匹配可用模型", extra={"tool": api_model})

                choice = data["choices"][0]["message"]
                usage = data.get("usage", {}) or {}
                calls: list[ToolCall] = []
                for tc in choice.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args or "{}")
                        except Exception:
                            args = {}
                    calls.append(ToolCall(tc.get("id") or "", fn.get("name") or "",
                                          args or {}))
                return LLMResult(
                    content=choice.get("content") or "",
                    tool_calls=calls,
                    prompt_tokens=usage.get("prompt_tokens", 0) or 0,
                    completion_tokens=usage.get("completion_tokens", 0) or 0,
                    model=api_model,
                    provider="openai",
                )

        raise last_error or LLMUpstreamError("模型调用失败：没有可用的模型。")

    async def summarize(self, text: str) -> str:
        """历史摘要压缩（Q12/Q41 模型分级：简单任务走轻量路径）。

        有密钥时用最小 prompt 调模型做抽取式摘要；离线时用规则式摘要，
        不消耗大模型预算，避免费用随对话轮次线性增长。
        """
        cfg = await self._runtime()
        key = (cfg.get("api_key") or "").strip()
        if key:
            try:
                res = await self._openai_chat(
                    [{"role": "system",
                      "content": "把下面的对话历史压缩成不超过80字的中文摘要，"
                                 "只保留旅行偏好、目的地、预算与结论。"},
                     {"role": "user", "content": text[:3000]}],
                    None, "deepseek-v4-flash", {**cfg, "api_key": key})
                if res.content.strip():
                    return res.content.strip()
            except Exception:
                pass
        # 规则式抽取摘要：取每轮用户消息要点
        lines = []
        for ln in text.splitlines():
            s = ln.strip()
            if s.startswith("用户：") or s.startswith("助手："):
                lines.append(s[:40])
        joined = "；".join(lines[-6:])
        return joined[:120] or text[:80]

    async def ping(self, model: str | None = None,
                   api_key: str | None = None) -> dict:
        """连通性自检：真实发一次最小请求，返回可用模型或可读错误。"""
        cfg = await self._runtime()
        key = (api_key or cfg.get("api_key") or "").strip()
        if not key:
            return {"ok": False, "message": "尚未配置 API Key。"}
        try:
            res = await self._openai_chat(
                [{"role": "user", "content": "ping"}], None, model, {**cfg, "api_key": key})
        except LLMUpstreamError as exc:
            return {"ok": False, "message": exc.message, "status": exc.status}
        except Exception as exc:                                  # noqa: BLE001
            return {"ok": False, "message": f"调用失败：{exc}"}
        return {"ok": True, "message": f"连接成功，实际使用模型：{res.model}",
                "model_used": res.model,
                "usage": {"prompt_tokens": res.prompt_tokens,
                          "completion_tokens": res.completion_tokens}}

    def supports_llm_planning(self) -> bool:
        return bool(settings.llm_api_key)


llm = LLMAdapter()
