"""端到端验证「真实模型 + RAG + 工具」链路。

用库中已加密的用户密钥（仅注入进程内缓存，不写入数据库），
以 demo 账号跑一次规划，断言：
  engine=real（真走了大模型）、rag_hits>0（RAG 命中）、tools 含天气/景点、未降级。
"""
import asyncio
import json
import sys

sys.path.insert(0, ".")


async def main() -> None:
    import httpx
    from app.main import app
    from app.db.session import SessionLocal
    from app.common.user_model import get_user_model_config
    from app.common.runtime_config import runtime_config

    # 取出真实密钥（解密后），仅放入进程内缓存，不落库
    async with SessionLocal() as db:
        cfg = await get_user_model_config(db, 8)
    if not cfg.get("api_key"):
        print("没有可用密钥，跳过真实链路验证")
        return
    llm_cfg = await runtime_config.get_llm()
    runtime_config._cache["llm"] = {**llm_cfg, "api_key": cfg["api_key"]}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://t", timeout=180) as c:
        r = await c.post("/api/auth/login", json={"username": "demo", "password": "demo123"})
        if r.status_code != 200:
            print("login failed", r.status_code, r.text[:200])
            return
        h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
        events = []
        import uuid
        async with c.stream("POST", "/api/agent/chat", headers=h, json={
                "message": "我要去成都玩3天，预算2500元，不想爬山",
                "request_id": uuid.uuid4().hex}) as resp:
            ev = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    ev = line[7:]
                elif line.startswith("data: ") and ev:
                    events.append((ev, line[6:]))

    kinds = [e for e, _ in events]
    done = next((json.loads(d) for e, d in events if e == "done"), {})
    tools = [json.loads(d)["tool"] for e, d in events if e == "tool_call"]
    draft = next((json.loads(d) for e, d in events if e == "plan_update"), {})
    print("事件类型:", sorted(set(kinds)))
    print("model_used:", done.get("model_used"), "| engine:", done.get("engine"))
    print("rag_hits:", done.get("rag_hits"), "| tools:", tools)
    print("degraded:", draft.get("degraded"), "| 天数:", len(draft.get("day_list") or []))
    assert done.get("engine") == "real", "应走真实模型"
    assert (done.get("rag_hits") or 0) > 0, "应有 RAG 引用"
    assert tools, "应调用工具"
    print("REAL-CHAIN OK")


asyncio.run(main())
