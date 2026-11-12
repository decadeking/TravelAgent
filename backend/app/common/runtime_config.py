"""运行时配置：LLM 模型列表 / 向量模型 / 知识库参数。

管理员在「设置」中修改后写入 system_settings 表，进程内缓存并即时生效
（无需重启）。未配置时回落到环境变量默认值。
"""
from __future__ import annotations

import json
from typing import Any

from .config import settings
from .crypto import decrypt_secret, encrypt_secret

_LLM_KEY = "llm"
_RAG_KEY = "rag"
# 需要密文落库的字段（明文密钥绝不写入 system_settings）
_SECRET_FIELDS = {"llm": ("api_key",), "rag": ("embedding_api_key",)}


def default_llm() -> dict[str, Any]:
    """模型目录。

    `id` 是展示/选择用的稳定标识，`api_model` 是真正发给上游的模型名，
    `fallbacks` 是上游报「模型不存在」时按序自动重试的候选名 —— 这样
    无论账号实际开通的是哪一代 DeepSeek 模型，都能自动匹配到可用模型。
    """
    return {
        "provider": "deepseek",
        "base_url": settings.llm_base_url or "https://api.deepseek.com/v1",
        "api_key": settings.llm_api_key,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "default_model": "deepseek-v4-flash",
        "models": [
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "provider": "deepseek",
             "description": "快速通用，日常行程规划首选",
             "api_model": "deepseek-v4-flash",
             "fallbacks": ["deepseek-chat", "deepseek-v3"]},
            {"id": "deepseek-4.1-flash", "name": "DeepSeek 4.1 Flash", "provider": "deepseek",
             "description": "新一代快速模型，中文理解更强",
             "api_model": "deepseek-4.1-flash",
             "fallbacks": ["deepseek-chat", "deepseek-reasoner"]},
        ],
    }


def model_catalog(cfg: dict) -> dict[str, dict]:
    return {m.get("id", ""): m for m in (cfg.get("models") or []) if m.get("id")}


def resolve_model_chain(cfg: dict, chosen: str | None) -> list[str]:
    """把展示用模型 id 解析成「真实上游模型名」的尝试链。"""
    chosen = chosen or cfg.get("default_model") or "deepseek-v4-flash"
    entry = model_catalog(cfg).get(chosen) or {}
    primary = entry.get("api_model") or chosen
    chain = [primary]
    for alt in entry.get("fallbacks") or []:
        if alt and alt not in chain:
            chain.append(alt)
    return chain


def default_rag() -> dict[str, Any]:
    return {
        "enabled": settings.rag_enabled,
        "vector_backend": settings.vector_backend,
        "vector_db_url": settings.vector_db_url,
        "vector_hnsw_ef_search": settings.vector_hnsw_ef_search,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "embedding_base_url": settings.embedding_base_url,
        "embedding_api_key": "",
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "topk": settings.rag_topk,
        "score_threshold": settings.rag_score_threshold,
        "rerank": settings.rag_rerank,
    }


def vector_model_ready(cfg: dict) -> tuple[bool, str]:
    """判断「向量模型」是否已配置——决定知识文档上传是否开放。

    约定：内置离线向量（hash）视为已就绪；切换为真实向量模型（openai 等）
    时必须有密钥与模型名，否则知识文档上传返回「该功能暂未开放」。
    """
    if not cfg.get("enabled", True):
        return False, "知识库功能已被管理员停用，该功能暂未开放"
    provider = (cfg.get("embedding_provider") or "").strip()
    if not provider:
        return False, "管理员尚未配置向量模型，该功能暂未开放"
    if provider == "hash":
        return True, ""
    if not (cfg.get("embedding_model") or "").strip():
        return False, "管理员尚未配置向量模型名称，该功能暂未开放"
    key = (cfg.get("embedding_api_key") or settings.embedding_api_key
           or settings.llm_api_key or "").strip()
    if not key:
        return False, "管理员尚未配置向量模型密钥，该功能暂未开放"
    return True, ""


class RuntimeConfig:
    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    async def _load(self, key: str, fallback: dict) -> dict:
        if key in self._cache:
            return self._cache[key]
        value = dict(fallback)
        try:
            from ..db.models import SystemSetting
            from ..db.session import SessionLocal
            from sqlalchemy import select

            async with SessionLocal() as db:
                row = await db.get(SystemSetting, key)
                if row and row.value:
                    stored = json.loads(row.value)
                    if isinstance(stored, dict):
                        value.update(stored)
        except Exception:
            pass
        # 落库字段解密后再交还调用方（缓存里保存明文，落库时再加密）
        for field in _SECRET_FIELDS.get(key, ()):
            value[field] = decrypt_secret(value.get(field))
        self._cache[key] = value
        return value

    async def get_llm(self) -> dict:
        cfg = await self._load(_LLM_KEY, default_llm())
        # 模型列表为固定配置，始终返回；无 Key 时由适配器自动回落到离线模拟
        cfg.setdefault("default_model", "deepseek-v4-flash")
        return cfg

    async def get_rag(self) -> dict:
        return await self._load(_RAG_KEY, default_rag())

    async def set(self, key: str, value: dict, *, merge: bool = True) -> dict:
        from ..db.models import SystemSetting
        from ..db.session import SessionLocal

        current = await self._load(key, default_llm() if key == _LLM_KEY else default_rag())
        new_value = {**current, **value} if merge else dict(value)
        # 落库前加密密钥字段；进程内缓存保留明文供适配器使用
        persisted = dict(new_value)
        for field in _SECRET_FIELDS.get(key, ()):
            persisted[field] = encrypt_secret(new_value.get(field))
        async with SessionLocal() as db:
            row = await db.get(SystemSetting, key)
            payload = json.dumps(persisted, ensure_ascii=False)
            if row:
                row.value = payload
            else:
                db.add(SystemSetting(key=key, value=payload))
            await db.commit()
        self._cache[key] = new_value
        return new_value

    async def invalidate(self, key: str | None = None) -> None:
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


runtime_config = RuntimeConfig()
