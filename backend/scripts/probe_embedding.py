"""向量模型有效性探针：确认「真实向量模型」是否真的生效（而不是静默回落 hash）。

检查项：
1. 运行时配置（provider / model / dim / base_url / 是否有密钥）
2. 直接调用 {base_url}/embeddings，看接口是否可用、返回维度
3. 调用 Embedder.embed()，与本地 hash 向量对比——若完全相同说明已静默回落 hash
4. 语义质量对比：语义相近 vs 无关文本的余弦相似度
5. 端到端检索：重建索引后按探针查询，打印命中块与分数、向量库后端

用法：python scripts/probe_embedding.py
"""
from __future__ import annotations

import asyncio
import sys

import httpx

sys.path.insert(0, ".")


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


async def main() -> None:
    from app.common.config import settings
    from app.common.runtime_config import vector_model_ready
    from app.services.agent_service.rag.embeddings import Embedder, _hash_embed
    from app.services.agent_service.rag.retriever import retriever
    from app.common.runtime_config import runtime_config

    cfg = await runtime_config.get_rag()
    ready, reason = vector_model_ready(cfg)
    provider = cfg.get("embedding_provider")
    dim = int(cfg.get("embedding_dim") or settings.embedding_dim)
    model = cfg.get("embedding_model")
    base_url = (cfg.get("embedding_base_url") or settings.embedding_base_url
                or settings.llm_base_url).rstrip("/")
    key = (cfg.get("embedding_api_key") or settings.embedding_api_key
           or settings.llm_api_key or "")

    print("=" * 62)
    print("1) 运行时配置")
    print(f"   vector_backend    = {cfg.get('vector_backend')}")
    print(f"   embedding_provider= {provider}")
    print(f"   embedding_model   = {model}")
    print(f"   embedding_dim     = {dim}")
    print(f"   embedding_base_url= {base_url}")
    print(f"   has_api_key       = {bool(key)}  上传闸门 ready={ready} {reason}")

    print("=" * 62)
    print("2) 直接请求 /embeddings（判断真实接口是否可用）")
    direct: list[list[float]] | None = None
    if provider == "openai" and key:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"{base_url}/embeddings",
                                 headers={"Authorization": f"Bearer {key}"},
                                 json={"model": model, "input": ["成都熊猫基地门票"]})
            print(f"   HTTP {r.status_code}")
            if r.status_code == 200:
                direct = [r.json()["data"][0]["embedding"]]
                print(f"   返回维度 = {len(direct[0])}")
            else:
                print(f"   错误响应 = {r.text[:300]}")
        except Exception as exc:
            print(f"   请求异常 = {type(exc).__name__}: {exc}")
    else:
        print("   provider 非 openai 或缺密钥，跳过")

    print("=" * 62)
    print("3) Embedder.embed() 是否静默回落 hash")
    emb = Embedder()
    probe = "成都熊猫基地门票多少钱"
    got = (await emb.embed([probe]))[0]
    local_hash = _hash_embed(probe, dim)
    same = all(abs(a - b) < 1e-9 for a, b in zip(got, local_hash))
    print(f"   向量维度 = {len(got)}")
    print(f"   与本地 hash 向量一致 = {same}  → {'【已回落 hash】' if same else '【真实模型向量】'}")
    if not same and direct:
        d = _cos(got, direct[0])
        print(f"   与直连接口返回向量的余弦相似度 = {d:.4f}（应≈1，证明确实走真实接口）")

    print("=" * 62)
    print("4) 语义质量：相近 vs 无关")
    pairs = (
        ("语义相近：熊猫基地 / 看大熊猫",
         "成都熊猫基地门票", "成都哪里可以看大熊猫、票价多少"),
        ("无关对照：熊猫基地 / 西湖",
         "成都熊猫基地门票", "杭州西湖游船票价"),
        ("近义改写：亲子 / 带娃",
         "适合带孩子去的景点", "亲子游好去处推荐"),
    )
    texts = [t for _, a, b in pairs for t in (a, b)]
    vecs = await emb.embed(texts)
    for (label, a, b), i in zip(pairs, range(0, len(texts), 2)):
        print(f"   {label}: cos={_cos(vecs[i], vecs[i + 1]):.4f}")

    print("=" * 62)
    print("5) 端到端：重建索引 → 检索")
    chunks = await retriever.rebuild()
    print(f"   索引重建完成：backend={retriever.backend} chunks={chunks}")
    hits = await retriever.retrieve("成都熊猫基地门票多少钱，开放时间", topk=3)
    for h in hits:
        print(f"   - score={h['score']:.4f} city={h['city']} title={h['title']} "
              f"text={h['text'][:60]}…")

    from app.db.session import engine
    await engine.dispose()


asyncio.run(main())
