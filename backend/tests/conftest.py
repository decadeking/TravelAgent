"""pytest 公共夹具：临时 SQLite + 内存 KV，避免污染开发库。"""
from __future__ import annotations

import os
from pathlib import Path

# 必须在导入 app 之前设置环境变量（测试与生产环境隔离）
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_travelagent.db"
os.environ["KV_BACKEND"] = "memory"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["VECTOR_BACKEND"] = "memory"
os.environ["EMBEDDING_PROVIDER"] = "hash"
# 测试禁用启动后台迁移任务，避免与用例查询竞争共享 SQLite 连接
os.environ["AUTO_MIGRATE"] = "0"
# 测试禁用提醒调度器，避免后台轮询干扰用例
os.environ["REMINDER_LOOP"] = "0"

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.db.seed import seed  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402

_DB = Path(__file__).resolve().parents[1] / "test_travelagent.db"


@pytest.fixture(scope="session", autouse=True)
def _clean_db():
    if _DB.exists():
        _DB.unlink()
    yield
    from app.db.session import engine

    engine.sync_engine.dispose()
    try:
        if _DB.exists():
            _DB.unlink()
    except PermissionError:
        pass


@pytest.fixture(autouse=True)
def _reset_state():
    """每个用例前重置进程内全局态（熔断器 / 故障演练 / 模型缓存），
    避免用例间相互串扰——这些是生产环境的运行时状态，测试需隔离。"""
    from app.common import circuit_breaker, fault
    from app.services.agent_service.llm import adapter as llm_adapter

    circuit_breaker._registry.clear()
    fault.fault.reset()
    llm_adapter._WORKING_MODEL.clear()
    yield


@pytest_asyncio.fixture
async def client():
    await init_db()
    async with SessionLocal() as db:
        await seed(db)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client):
    r = await client.post("/api/auth/login", json={"username": "demo", "password": "demo123"})
    token = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def parse_sse(text: str) -> list[tuple[str, str]]:
    events = []
    event = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: ") and event:
            events.append((event, line[6:]))
    return events
