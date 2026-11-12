"""RAG 单测：切片策略 + 检索命中。"""
from __future__ import annotations

from app.services.agent_service.rag.chunker import chunk_documents
from app.services.agent_service.rag.retriever import retriever


def test_chunking_produces_metadata_and_overlap():
    docs = [{"city": "成都", "title": "成都攻略",
             "content": "成都是一座来了就不想走的城市。" * 40}]
    chunks = chunk_documents(docs, chunk_size=120, overlap=30)
    assert len(chunks) > 1
    for c in chunks:
        assert c.text.strip()
        assert c.metadata["city"] == "成都"
        assert c.chunk_id
    # 相邻块应存在重叠（前一块尾部字符出现在后一块中）
    tail = chunks[0].text[-15:]
    assert tail in chunks[1].text


async def test_retrieval_returns_relevant_chunks():
    hits = await retriever.retrieve("成都 大熊猫 门票 开放时间", city="成都")
    assert hits, "应至少检索到一个相关块"
    joined = " ".join(h["text"] for h in hits)
    assert ("成都" in joined) or ("熊猫" in joined)
    # 检索结果带城市元数据与分数
    assert all("score" in h and h["score"] >= 0 for h in hits)


async def test_retrieval_city_filter():
    hits = await retriever.retrieve("故宫 门票", city="北京")
    assert hits
    assert all(h["city"] in ("北京", "通用") for h in hits)
