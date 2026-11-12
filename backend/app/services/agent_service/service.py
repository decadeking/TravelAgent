"""agent_service：会话管理、状态图编排、SSE 推送。

把稳定性机制串到一次规划请求的完整路径上：
  鉴权 → 配额检查 → 幂等占位 → 分布式锁 → 载入会话 →
  运行状态图（SSE 流式） → 落库/记忆 → 释放锁 → 完成幂等
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ...common import context
from ...common.config import settings
from ...common.distlock import DistributedLock, plan_lock_key
from ...common.errors import AppError, RateLimitError
from ...common.fault import fault
from ...common.idempotency import IdemState, IdempotencyGuard
from ...common.logging import get_logger
from ...common.metrics import metrics
from ...common.quota import add_tokens, check_quota
from ...common.ratelimit import check_global_rate_limit, check_user_rate_limit, llm_limiter
from ...common.tracing import tracer
from ...db.models import LLMCallLog
from ...db.session import SessionLocal
from ...services.tool_service import tools
from .core.graph import travel_graph
from .core.nodes import assemble_draft, extract_slots
from .guard.prompt_guard import prompt_guard
from .llm.adapter import LLMUpstreamError
from .memory.long_term import extract_preferences, load_preferences, save_preferences
from .memory.short_term import session_memory
from .sse.manager import Connection, manager

logger = get_logger("agent_service")

_MODIFY_WORDS = r"换|改|调整|便宜|贵|加个|去掉|删|不要|多安排|少安排|重排|再来"


def sse_format(event: str, data: Any, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _degraded_draft(city: str, days: int, budget: float) -> dict:
    """降级方案：不依赖大模型，用本地规则 + 工具生成参考行程。"""
    state = {
        "slots": {"destination": city, "days": days, "budget": budget, "preferences": []},
        "plan_requests": {"city": city, "days": days, "budget": budget},
        "tool_results": {
            "search_poi": tools.search_poi(city, topk=12),
            "get_weather": tools.get_weather(city, days),
            "estimate_budget": tools.estimate_budget(city, days, budget),
        },
        "citations": [],
    }
    draft = assemble_draft(state)
    draft["warnings"].append("当前为降级模式（智能规划维护中），以上为规则化参考行程")
    draft["degraded"] = True
    return draft


_IMAGE_REF = re.compile(r"/api/media/(\d+)")


async def _collect_images(db: AsyncSession, message: str) -> list[str]:
    """把消息里的 /api/media/{id} 图片引用转成 base64 data URL（多模态喂给模型）。

    前端上传图片后只会把「【图片】/api/media/12」拼进文本——模型访问不了本机 URL，
    因此在这里从后端资源文件夹读出文件本体，编码为 data URL，
    由 llm adapter 以 OpenAI 兼容的 image_url 多模态格式随最后一条用户消息发送。
    """
    from ...db.models import Media
    urls: list[str] = []
    for media_id in list(dict.fromkeys(int(i) for i in _IMAGE_REF.findall(message or "")))[:3]:
        row = await db.get(Media, media_id)
        if row is None or not (row.mime or "").startswith("image/") \
                or (row.mime or "").startswith("image/svg"):
            continue                       # SVG 可能含脚本，不喂给模型
        abs_path = Path(__file__).resolve().parents[3] / "static" / "uploads" / row.path
        if not abs_path.exists() or abs_path.stat().st_size > 5 * 1024 * 1024:
            continue
        raw = await asyncio.to_thread(abs_path.read_bytes)
        urls.append(f"data:{row.mime};base64,{base64.b64encode(raw).decode()}")
    return urls


async def handle_chat(
    *, user_id: int, username: str, session_id: str, message: str, request_id: str,
    conn: Connection, db: AsyncSession, model: str | None = None,
    tools_enabled: list[str] | None = None,
) -> None:
    """在后台任务中执行一次完整规划，事件推入 conn.queue。"""
    idem = IdempotencyGuard()
    lock = DistributedLock(plan_lock_key(user_id))
    start = time.time()
    state: dict = {}
    try:
        # 1) 限流（用户级 + 全局）
        await check_user_rate_limit(user_id)
        await check_global_rate_limit()
        # 2) 配额检查
        await check_quota(user_id)
        # 3) 幂等占位
        res = await idem.begin(request_id)
        if res.state == IdemState.IN_PROGRESS:
            await manager.send(conn, "error",
                               {"code": 40901, "message": "该请求正在处理中，请勿重复提交"})
            return
        if res.state == IdemState.DONE:
            await manager.send(conn, "token", {"text": "（该请求已处理，返回缓存结果）\n"})
            await manager.send(conn, "plan_update", res.result or {})
            await manager.send(conn, "done", {"cached": True, "session_id": session_id,
                                              "request_id": request_id})
            return
        # 4) 分布式锁：同一用户同时只允许一个规划任务
        if not await lock.acquire():
            await manager.send(conn, "error",
                               {"code": 40902, "message": "已有规划任务进行中，请稍后再试"})
            await idem.fail(request_id)
            return

        await manager.send(conn, "meta", {"session_id": session_id,
                                          "trace_id": context.get_trace_id()})

        # 5) 载入会话（断线恢复）
        saved = await session_memory.load(session_id)
        existing_draft = saved.get("plan_draft")
        is_revision = bool(existing_draft) and bool(re.search(_MODIFY_WORDS, message))

        prefs = await load_preferences(db, user_id)
        # 用户级模型配置：用户自己的 Key / 模型选择（为空则用全局配置）
        from ...common.user_model import get_user_model_config
        user_model = await get_user_model_config(db, user_id)
        chosen_model = model or user_model.get("model") or None
        messages = list(saved.get("messages", []))
        messages.append({"role": "user", "content": message})

        state = {
            "session_id": session_id,
            "user_id": user_id,
            "messages": messages,
            "slots": saved.get("slots", {}),
            "prefs": prefs,
            "plan_draft": existing_draft,
            "revision_count": (saved.get("revision_count", 0) + 1) if is_revision else 0,
            "tool_results": {},
            "citations": [],
            "warnings": [],
            "model": chosen_model,
            "llm_api_key": user_model.get("api_key") or None,
            "tools_enabled": tools_enabled,
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
        # 本轮消息里引用的上传图片 → base64 data URL（仅本次运行使用，不进 Redis 持久化）
        state["images"] = await _collect_images(db, message)

        async def emit(event: str, data: Any) -> None:
            sent = await manager.send(conn, event, data)
            # 双保险断开检测：队列连续两次写入失败（客户端已停止消费）→ 判定断开
            if not sent and conn.fail_count >= 2:
                raise asyncio.CancelledError

        async def checkpointer(s: dict) -> None:
            await session_memory.save(session_id, s)

        # 6) 运行状态图（受大模型并发信号量约束；整体 120 秒超时，Q14）
        try:
            async with llm_limiter:
                with tracer.span("agent.run", session_id=session_id):
                    state = await asyncio.wait_for(
                        travel_graph.run(state, emit=emit, checkpointer=checkpointer),
                        timeout=settings.plan_timeout_seconds)
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            # 超时不是报错，而是输出当前草稿并向用户说明（防死循环烧钱）
            logger.warning("规划整体超时", extra={"event": "plan_timeout"})
            draft = state.get("plan_draft") or _degraded_draft(
                (state.get("slots") or {}).get("destination") or "成都",
                int((state.get("slots") or {}).get("days") or 3),
                float((state.get("slots") or {}).get("budget") or 0))
            draft.setdefault("warnings", []).append(
                f"规划超过 {settings.plan_timeout_seconds} 秒上限，已输出当前进度草稿")
            await emit("token", {"text": "规划耗时超出预期，先给你当前进度的草稿，可继续让我调整。\n"})
            await emit("plan_update", draft)
            state["plan_draft"] = draft
            metrics.inc("degrade_total")
        except LLMUpstreamError as exc:
            # 大模型本身的问题（密钥/余额/模型/限流）→ 如实告知用户，再给参考模板
            logger.warning("大模型不可用，进入降级", extra={"event": "llm_degrade"})
            slots = state.get("slots", {})
            draft = _degraded_draft(
                slots.get("destination") or "成都",
                int(slots.get("days") or 3),
                float(slots.get("budget") or 0),
            )
            draft["llm_error"] = exc.message
            await emit("error", {"code": 50201, "message": exc.message,
                                 "fatal": False, "fallback": True})
            await emit("token", {"text": f"⚠️ 大模型调用失败：{exc.message}\n已切换为规则化参考行程。\n"})
            await emit("plan_update", draft)
            state["plan_draft"] = draft
            metrics.inc("degrade_total")
        except Exception as exc:
            # 其它异常（含熔断打开） → 降级而非雪崩
            logger.warning("规划失败，进入降级", exc_info=exc, extra={"event": "degrade"})
            slots = state.get("slots", {})
            city = slots.get("destination") or "成都"
            days = int(slots.get("days") or 3)
            budget = float(slots.get("budget") or 0)
            draft = _degraded_draft(city, days, budget)
            await emit("token", {"text": "智能规划暂时不可用，已切换为参考模板。\n"})
            await emit("plan_update", draft)
            state["plan_draft"] = draft
            metrics.inc("degrade_total")

        # 7) 落库与收尾
        # 把本轮助手回复写回会话消息：否则切页/刷新后只剩用户提问、对话内容丢失
        final_text = (state.get("assistant_message") or "").strip()
        if final_text and state["messages"] and state["messages"][-1].get("role") == "user":
            state["messages"].append({"role": "assistant", "content": final_text})
        # 上下文压缩：超过滑动窗口的历史由摘要替代（Q12/Q41，避免费用随轮次线性增长）
        msgs = state.get("messages", [])
        window = settings.context_max_turns * 2
        if len(msgs) > window + 2:
            older = msgs[:-window]
            text = "\n".join(f"{'用户' if m.get('role') == 'user' else '助手'}：{m.get('content', '')[:60]}"
                             for m in older if m.get("content"))
            from .llm.adapter import llm as _llm
            state["summary"] = await _llm.summarize(
                (state.get("summary", "") + "\n" + text).strip())
            state["messages"] = msgs[-window:]
        await session_memory.save(session_id, state)
        await _persist_session(db, session_id, user_id, state)
        # 规划生成成功 → 站内消息（仅「本会话首次生成行程」时提示，避免每轮刷屏）
        new_draft = state.get("plan_draft") or {}
        if new_draft and not existing_draft:
            from ...common.notify import notify
            await notify(db, user_id=user_id, kind="system", title="行程规划已生成",
                         content=f"{new_draft.get('title', '行程')}（{new_draft.get('days', 0)} 天 · "
                                 f"{new_draft.get('destination', '')}）",
                         link="/plan")
            await db.commit()
        # 长期记忆：抽取稳定偏好回写
        found = extract_preferences(message)
        if found:
            await save_preferences(db, user_id, found)
            await emit("memory", {"saved": found})

        usage = state.get("token_usage", {})
        total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        if total_tokens:
            await add_tokens(user_id, total_tokens)
        await _log_llm_call(db, user_id, session_id, usage, start,
                            state.get("model_used"), request_id=request_id)

        draft = state.get("plan_draft") or {}
        await idem.complete(request_id, draft)
        model_used = state.get("model_used") or ""
        # 路径透明化：让用户/答辩能一眼看出本次是真实模型还是离线模拟、
        # 命中了多少 RAG 引用、调用了哪些工具、是否降级
        engine = "real" if state.get("provider_used") == "openai" else "offline"
        await emit("done", {
            "session_id": session_id,
            "request_id": request_id,
            "cached": False,
            "usage": usage,
            "revision_count": state.get("revision_count", 0),
            "within_budget": draft.get("within_budget", True),
            "trace_id": context.get_trace_id(),
            "model_used": model_used,
            "engine": engine,
            "degraded": bool(draft.get("degraded")),
            "rag_hits": len(state.get("citations") or []),
            "tools": list((state.get("tool_results") or {}).keys()),
        })
        metrics.inc("plan_success_total")
    except RateLimitError as exc:
        await manager.send(conn, "error", {"code": exc.code, "message": exc.message,
                                           "retry_after": getattr(exc, "retry_after", None)})
    except AppError as exc:
        await manager.send(conn, "error", {"code": exc.code, "message": exc.message})
    except asyncio.CancelledError:
        logger.info("规划任务被取消（客户端断开）", extra={"event": "cancelled"})
        raise
    except Exception as exc:
        logger.error("规划任务异常", exc_info=exc)
        await manager.send(conn, "error", {"code": 50001, "message": f"服务异常：{exc}"})
    finally:
        await lock.release()
        await manager.send(conn, "__close__", None)


async def _persist_session(db: AsyncSession, session_id: str, user_id: int,
                           state: dict) -> None:
    from sqlalchemy import select
    from ...db.models import AgentSession
    row = await db.scalar(select(AgentSession).where(AgentSession.session_id == session_id))
    payload = {
        "slots": state.get("slots", {}),
        "plan_draft": state.get("plan_draft"),
        "revision_count": state.get("revision_count", 0),
    }
    if row:
        row.state_json = json.dumps(payload, ensure_ascii=False)
        row.summary = (state.get("assistant_message") or "")[:200]
    else:
        db.add(AgentSession(
            session_id=session_id, user_id=user_id,
            state_json=json.dumps(payload, ensure_ascii=False),
            summary=(state.get("assistant_message") or "")[:200],
        ))
    await db.commit()


async def _log_llm_call(db: AsyncSession, user_id: int, session_id: str,
                        usage: dict, start: float, model_used: str | None = None,
                        request_id: str | None = None) -> None:
    """调用台账。request_id 唯一索引是幂等的数据库层最后兜底（Q32）：
    Redis 幂等失效导致重复执行时，重复台账会被唯一约束拒绝。"""
    try:
        db.add(LLMCallLog(
            user_id=user_id, session_id=session_id, trace_id=context.get_trace_id(),
            request_id=(request_id or None),
            model=model_used or (settings.llm_model if settings.llm_provider == "openai"
                                 else "mock-llm"),
            purpose="plan",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=round((time.time() - start) * 1000, 2),
            status="ok",
        ))
        await db.commit()
    except Exception:
        await db.rollback()


async def chat_event_stream(
    *, user_id: int, username: str, session_id: str, message: str, request_id: str,
    model: str | None = None, tools: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """SSE 生成器：连接管理 + 心跳 + 断开取消（双保险）。"""
    conn = Connection(conn_id=uuid.uuid4().hex[:12], user_id=user_id, session_id=session_id)
    await manager.register(conn)
    context.set_session_id(session_id)

    async with SessionLocal() as db:
        task = asyncio.create_task(handle_chat(
            user_id=user_id, username=username, session_id=session_id,
            message=message, request_id=request_id, conn=conn, db=db, model=model,
            tools_enabled=tools,
        ))
        conn.task = task
        seq = 0
        try:
            # 事件编号：前端按 (request_id, id) 去重，重连不重复渲染（Q28）
            yield "retry: 3000\n\n"
            while True:
                try:
                    event, data = await asyncio.wait_for(conn.queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield sse_format("ping", {"ts": int(time.time())})
                    continue
                if event == "__close__":
                    break
                seq += 1
                yield sse_format(event, data, event_id=seq)
        finally:
            await manager.cancel(conn)       # 断开清理：取消规划任务
            await manager.unregister(conn.conn_id)
            if not task.done():
                try:
                    await asyncio.wait_for(task, timeout=3)
                except Exception:
                    task.cancel()
