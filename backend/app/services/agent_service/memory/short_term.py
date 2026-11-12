"""短期记忆：Redis(或内存) 以 session_id 为键存对话历史与图状态，TTL 2 小时。

上下文组装策略：滑动窗口 + 摘要——最近 N 轮保留原文，更早的历史由摘要替代，
控制 token 随轮次线性膨胀。断线恢复会话即从这里读回状态。
"""
from __future__ import annotations

import json

from ....common.config import settings
from ....common.kvstore import get_kv


def _key(session_id: str) -> str:
    return f"session:{session_id}"


class SessionMemory:
    async def load(self, session_id: str) -> dict:
        raw = await get_kv().get(_key(session_id))
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    async def save(self, session_id: str, state: dict) -> None:
        # user_id 一并持久化：会话归属随上下文存进 Redis，
        # 供 chat/恢复接口校验「这个 session 是不是当前用户的」，防止跨用户串会话
        persist_keys = ("user_id", "messages", "slots", "plan_draft", "revision_count",
                        "summary", "citations", "assistant_message", "status")
        slim = {k: state.get(k) for k in persist_keys if k in state}
        await get_kv().set_json(_key(session_id), slim,
                                ex=settings.session_ttl_seconds)

    async def delete(self, session_id: str) -> None:
        await get_kv().delete(_key(session_id))

    def build_context(self, state: dict) -> list[dict]:
        """滑动窗口 + 摘要：最近 N 轮原文 + 更早历史摘要。"""
        messages: list[dict] = state.get("messages", [])
        max_turns = settings.context_max_turns
        recent = messages[-max_turns * 2:]
        ctx: list[dict] = []
        summary = state.get("summary")
        if summary:
            ctx.append({"role": "system", "content": f"早前对话摘要：{summary}"})
        ctx.extend(recent)
        return ctx


session_memory = SessionMemory()
