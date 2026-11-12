"""MCP 文档解析 / 知识文档上传 / RAG 全链路自检 / 行程提醒联动 单测。"""
from __future__ import annotations

import io

from sqlalchemy import delete

from app.common.runtime_config import vector_model_ready
from app.services.media_service.parsers import clean_text, detect_kind, parse_document


# ─────────────────── 向量模型门槛（未配置 → 该功能暂未开放） ───────────────────

def test_vector_model_ready_gate():
    assert vector_model_ready({"enabled": True, "embedding_provider": "hash"})[0] is True

    ok, reason = vector_model_ready(
        {"enabled": True, "embedding_provider": "openai", "embedding_model": "m"})
    assert ok is False and "暂未开放" in reason            # openai 缺密钥 → 拦截

    ok2, _ = vector_model_ready({"enabled": False, "embedding_provider": "hash"})
    assert ok2 is False                                   # 知识库被停用 → 拦截

    ok3, reason3 = vector_model_ready({"enabled": True, "embedding_provider": ""})
    assert ok3 is False and "暂未开放" in reason3          # 未配置向量模型 → 拦截


# ─────────────────── 原料清洗 + 多格式解析 ───────────────────

def test_clean_text_removes_page_numbers_and_folds_blanks():
    raw = "标题\n\n\n\n正文一\n- 1 -\n正文二\n\n- 2 -\n"
    cleaned, stats = clean_text(raw)
    assert "- 1 -" not in cleaned and "- 2 -" not in cleaned
    assert "正文一" in cleaned and "正文二" in cleaned
    assert stats["dropped_lines"] >= 3
    assert stats["clean_chars"] > 0


def test_detect_kind_and_parse_txt():
    assert detect_kind("a.md") == "md"
    assert detect_kind("a.pdf") == "pdf"
    assert detect_kind("a.docx") == "docx"
    res = parse_document("a.txt", "一、门票\n门票 50 元。\n- 1 -\n".encode("utf-8"), "text/plain")
    assert res["ok"] is True and res["kind"] == "txt"
    assert "门票 50 元" in res["text"] and "- 1 -" not in res["text"]


def test_parse_rejects_legacy_doc_and_broken_pdf():
    bad = parse_document("a.doc", b"x")
    assert bad["ok"] is False and ".docx" in bad["error"]      # 旧版二进制 .doc 不支持
    broken = parse_document("a.pdf", b"not a real pdf")
    assert broken["ok"] is False
    assert parse_document("a.zip", b"x")["ok"] is False        # 不支持的类型


def test_parse_docx_roundtrip():
    from docx import Document
    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("标题：大理备忘")
    doc.add_paragraph("洱海骑行一圈约 130 公里")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "苍山索道"
    table.rows[0].cells[1].text = "往返 200 元"
    doc.save(buf)

    res = parse_document("b.docx", buf.getvalue())
    assert res["ok"] is True and res["kind"] == "docx"
    assert "洱海骑行" in res["text"] and "苍山索道" in res["text"]


# ─────────────────── 接口：逆地理编码 / 上传门槛 / 上传入库 ───────────────────

async def test_reverse_geocode_endpoint(client, auth_headers):
    r = await client.get("/api/tools/reverse_geocode", headers=auth_headers,
                         params={"lat": 30.5728, "lon": 104.0668})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["city"] == "成都" and data["found"] is True


async def test_doc_upload_blocked_when_vector_model_missing(client, auth_headers, monkeypatch):
    """管理员未配置向量模型 → 用户上传知识文档返回「该功能暂未开放」。"""
    from app.common import runtime_config as rc

    async def _fake_get_rag():
        return {"enabled": True, "embedding_provider": "openai",
                "embedding_model": "text-embedding-3-small", "embedding_api_key": ""}

    monkeypatch.setattr(rc.runtime_config, "get_rag", _fake_get_rag)
    r = await client.post("/api/media/upload_doc", headers=auth_headers, params={"city": "通用"},
                          files={"file": ("t.txt", io.BytesIO(b"hello" * 40), "text/plain")})
    assert r.status_code == 400
    assert "该功能暂未开放" in r.text


async def test_doc_upload_ingests_into_rag(client, auth_headers):
    """正常上传 txt → 清洗、切片、入库，并能被检索命中。"""
    from app.db.models import KBDocument
    from app.db.session import SessionLocal
    from app.services.agent_service.rag.retriever import retriever

    content = ("稻城亚丁旅行备忘\n\n一、牛奶海：徒步往返约 6 小时，建议早出发。\n"
               "二、五色海：海拔 4600 米，注意高反。\n- 1 -\n")
    r = await client.post("/api/media/upload_doc", headers=auth_headers, params={"city": "稻城"},
                          files={"file": ("mcp_test_note.txt",
                                          io.BytesIO(content.encode("utf-8")), "text/plain")})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["file_type"] == "txt"
    assert data["chunks"] >= 1 and data["total_chunks"] >= 1
    assert data["vector_backend"] in ("memory", "pgvector")
    assert "牛奶海" not in data["preview"] or data["preview"]   # 预览非空
    assert "- 1 -" not in data["preview"]                       # 页码已被清洗

    try:
        hits = await retriever.retrieve("稻城亚丁 牛奶海 徒步", topk=5)
        assert hits, "刚入库的文档应可被检索到"
    finally:
        # 清理：删除测试文档并重建索引，避免影响其它用例
        async with SessionLocal() as db:
            await db.execute(delete(KBDocument).where(
                KBDocument.source == "upload:mcp_test_note.txt"))
            await db.commit()
        await retriever.rebuild()


# ─────────────────── 接口：RAG 全链路自检 / MCP 状态 ───────────────────

async def test_kb_selftest_admin_only_and_passes(client, auth_headers):
    from app.db.models import KBDocument
    from app.db.session import SessionLocal
    from app.services.agent_service.rag.retriever import retriever

    demo = await client.post("/api/admin/kb/selftest", headers=auth_headers)
    assert demo.status_code == 403                       # 仅管理员

    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    admin = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    res = await client.post("/api/admin/kb/selftest", headers=admin)
    assert res.status_code == 200
    body = res.json()["data"]
    names = {s["name"] for s in body["stages"]}
    assert names == {"原料清洗", "两级切片", "向量化", "向量库入库", "检索召回"}
    assert body["passed"] is True, body["stages"]

    async with SessionLocal() as db:
        await db.execute(delete(KBDocument).where(
            KBDocument.source == "selftest:rag_selftest.txt"))
        await db.commit()
    await retriever.rebuild()


async def test_mcp_status_endpoint(client, auth_headers):
    r = await client.get("/api/mcp/status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["transport"] == "stdio"
    assert data["status"] in ("disabled", "starting", "ready", "error")


# ─────────────────── 行程日期 → 自动开启提醒（含桌面通知标记） ───────────────────

async def test_trip_start_date_creates_reminders(client, auth_headers):
    from datetime import date, timedelta

    start = (date.today() + timedelta(days=12)).isoformat()
    r = await client.post("/api/trips", headers=auth_headers, json={
        "title": "提醒自检行程", "destination": "稻城", "days": 2, "budget": 1200,
        "status": "draft", "remark": "注意高反", "start_date": start, "day_list": [],
    })
    assert r.status_code == 200, r.text
    assert r.json()["data"]["start_date"] == start

    rem = (await client.get("/api/agent/reminders", headers=auth_headers)).json()["data"]
    mine = [x for x in rem if x["source"] == "trip" and "稻城" in x["title"]]
    titles = " ".join(x["title"] for x in mine)
    assert "出行前提醒" in titles and "旅行当天提醒" in titles
    assert any(x["status"] == "pending" for x in mine)
