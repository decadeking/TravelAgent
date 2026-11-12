"""全局配置。

使用 pydantic-settings 从环境变量 / .env 读取，所有默认值都能在
「零外部服务」模式下直接运行（SQLite + 内存 KV + Mock LLM）。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- 应用 ----
    app_name: str = "交互式旅行规划智能体"
    app_version: str = "1.0.0"
    debug: bool = True

    # ---- LLM ----
    llm_provider: str = Field(default="mock")          # mock | openai
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_fallback_model: str = "deepseek-chat"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048
    llm_timeout_seconds: float = 60.0

    # ---- 存储 ----
    database_url: str = "sqlite+aiosqlite:///./travelagent.db"

    # ---- 向量库（RAG 生产形态：PostgreSQL + pgvector） ----
    vector_backend: str = Field(default="memory")        # memory | pgvector
    vector_db_url: str = "postgresql://postgres:postgres@127.0.0.1:5432/travelvec"
    vector_hnsw_ef_search: int = 40                       # 召回/时延平衡参数

    # ---- Embedding（向量模型可配置） ----
    embedding_provider: str = Field(default="hash")       # hash | openai
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 512
    embedding_base_url: str = ""                          # 为空则复用 LLM_BASE_URL
    embedding_api_key: str = ""                           # 为空则复用 LLM_API_KEY

    # ---- KV ----
    kv_backend: str = Field(default="memory")          # memory | redis
    redis_url: str = "redis://localhost:6379/0"

    # ---- JWT ----
    jwt_secret: str = "travel-agent-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    # ---- 密钥加密（API Key 不以明文落库） ----
    secret_encryption_key: str = ""       # 为空则由 JWT_SECRET 派生

    # ---- 限流 ----
    rate_limit_per_user_per_minute: int = 10
    rate_limit_global_qps: int = 200
    llm_max_concurrency: int = 20

    # ---- 熔断 ----
    breaker_window_seconds: int = 10
    breaker_failure_threshold: float = 0.5
    breaker_min_samples: int = 5
    breaker_cooldown_seconds: int = 30
    breaker_half_open_probes: int = 3

    # ---- 重试 ----
    retry_max_attempts: int = 2
    retry_base_delay: float = 0.5
    retry_jitter: float = 0.2

    # ---- 幂等 / 锁 ----
    idempotency_ttl_seconds: int = 600
    plan_lock_ttl_seconds: int = 60
    plan_lock_watchdog_interval: int = 20

    # ---- 会话 / 记忆 ----
    session_ttl_seconds: int = 7200
    context_max_turns: int = 8
    plan_timeout_seconds: int = 120
    revision_max: int = 3

    # ---- RAG ----
    rag_enabled: bool = True
    rag_topk: int = 5
    rag_chunk_size: int = 380
    rag_chunk_overlap: int = 50
    rag_score_threshold: float = 0.5
    rag_rerank: bool = True

    # ---- Token 配额 ----
    token_daily_quota: int = 100000
    token_warn_ratio: float = 0.8      # 用量超过该比例（占配额）时发提醒

    # ---- MCP（工具以 MCP 子进程方式提供，失败自动旁路到原生实现） ----
    mcp_enabled: bool = False
    mcp_python: str = ""                                  # 为空则用当前解释器
    mcp_server_module: str = "app.services.mcp_service.server"
    mcp_server_cwd: str = ""                              # 为空则用 backend 根目录
    mcp_health_interval: int = 60                         # 健康检查间隔（秒）
    mcp_call_timeout: float = 15.0                        # 单次 MCP 工具调用超时

    # ---- 文档入库（pdf / wps(docx) / txt / md → RAG 知识库） ----
    doc_upload_max_bytes: int = 10 * 1024 * 1024          # 单文档上限 10MB

    # ---- CORS ----
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
