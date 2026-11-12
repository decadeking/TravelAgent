-- pgvector 初始化：知识库向量表（RAG 生产形态）
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_chunks (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      BIGINT      NOT NULL,
    city        TEXT        NOT NULL DEFAULT '',
    title       TEXT        NOT NULL DEFAULT '',
    chunk_index INT         NOT NULL DEFAULT 0,
    text        TEXT        NOT NULL,
    embedding   vector(512) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 元数据过滤（先按城市过滤再向量检索）
CREATE INDEX IF NOT EXISTS idx_kb_chunks_city ON kb_chunks (city);

-- HNSW 向量索引：召回高、支持增量写入（m=16, ef_construction=64）
CREATE INDEX IF NOT EXISTS idx_kb_chunks_hnsw
    ON kb_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
