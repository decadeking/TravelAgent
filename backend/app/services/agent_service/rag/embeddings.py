"""Embedding：向量模型可配置（provider / model / dim / base_url / api_key）。

- hash：本地确定性特征哈希向量（零依赖，离线可用），投影到配置维度并归一化。
  查询与语料用同一编码方式，保证在同一向量空间可比。
- openai：调用真实 OpenAI 兼容 embedding 接口（如 text-embedding-3-small），
  失败自动回落到 hash，保证 RAG 链路不中断。

配置来源：管理员运行时配置（system_settings.rag），未配置时回落到环境变量。
"""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from ....common.config import settings


def _tokenize(text: str) -> list[str]:
    """中英混合分词：中文取单字 + 双字词组，英文/数字取词。"""
    text = text.lower()
    tokens: list[str] = []
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend(cjk)
    tokens.extend("".join(cjk[i:i + 2]) for i in range(len(cjk) - 1))
    tokens.extend(re.findall(r"[a-z0-9]+", text))
    return tokens


def _hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    for tok in _tokenize(text):
        h = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


class Embedder:
    def __init__(self, provider: str | None = None, dim: int | None = None,
                 model: str | None = None) -> None:
        self.provider = provider or settings.embedding_provider
        self.dim = dim or settings.embedding_dim
        self.model = model or settings.embedding_model

    async def _runtime(self) -> dict:
        from ....common.runtime_config import runtime_config
        return await runtime_config.get_rag()

    async def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        """编码文本。is_query=True 表示查询侧。

        指令前缀（Q18）：部分模型对 query/document 支持不同前缀，用对前缀
        能明显提升检索效果。hash 后端以「查询扩展词」代替前缀；openai 后端
        按配置决定是否加 instruction 前缀。
        """
        cfg = await self._runtime()
        provider = cfg.get("embedding_provider") or self.provider
        dim = int(cfg.get("embedding_dim") or self.dim)
        model = cfg.get("embedding_model") or self.model
        if provider == "openai":
            api_key = cfg.get("embedding_api_key") or settings.embedding_api_key \
                or settings.llm_api_key
            base_url = (cfg.get("embedding_base_url") or settings.embedding_base_url
                        or settings.llm_base_url).rstrip("/")
            if api_key:
                try:
                    prefixed = ([f"为该文本生成检索向量：{t}" for t in texts]
                                if cfg.get("embedding_prefix_doc")
                                else texts)
                    if is_query and cfg.get("embedding_prefix_query"):
                        prefixed = [f"为以下查询生成检索向量：{t}" for t in texts]
                    return await self._openai_embed(prefixed, base_url, api_key, model)
                except Exception:
                    pass
        if is_query:
            # 查询侧轻量扩展：同义词改写，提升 hash 空间召回
            from .retriever import Retriever
            texts = [Retriever.rewrite_query(t) for t in texts]
        return [_hash_embed(t, dim) for t in texts]

    async def _openai_embed(self, texts: list[str], base_url: str, api_key: str,
                            model: str) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            return [d["embedding"] for d in data["data"]]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot  # 已归一化
