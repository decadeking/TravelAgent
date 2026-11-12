<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/http'
import type { AdminSettings } from '@/types'

const loading = ref(true)
const error = ref('')
const flash = ref('')

const savingLlm = ref(false)
const savingRag = ref(false)

const kbDocuments = ref(0)
const kbChunks = ref(0)
const vectorBackend = ref('memory')

const llm = reactive({
  base_url: '',
  api_key: '',
  default_model: '',
  temperature: 0.7,
  max_tokens: 2048,
})

const rag = reactive({
  vector_backend: 'memory',
  vector_db_url: '',
  vector_hnsw_ef_search: 40,
  embedding_provider: 'hash',
  embedding_model: 'text-embedding-3-small',
  embedding_dim: 512,
  embedding_base_url: '',
  embedding_api_key: '',
  has_embedding_key: false,
  chunk_size: 400,
  chunk_overlap: 60,
  topk: 5,
  score_threshold: 0.5,
  rerank: true,
})

// 知识文档上传开放状态（与用户端「RAG 知识库」区块对齐）
const docUploadReady = ref(true)
const docUploadReason = ref('')

function notify(text: string) {
  flash.value = text
  window.setTimeout(() => {
    flash.value = ''
  }, 3200)
}

function applySettings(data: AdminSettings) {
  if (data.llm) {
    llm.base_url = data.llm.base_url ?? ''
    llm.api_key = ''
    llm.default_model = data.llm.default_model ?? ''
    llm.temperature = Number(data.llm.temperature ?? 0.7)
    llm.max_tokens = Number(data.llm.max_tokens ?? 2048)
  }
  if (data.rag) {
    rag.vector_backend = data.rag.vector_backend ?? 'memory'
    rag.vector_db_url = data.rag.vector_db_url ?? ''
    rag.vector_hnsw_ef_search = Number(data.rag.vector_hnsw_ef_search ?? 40)
    rag.embedding_provider = data.rag.embedding_provider ?? 'hash'
    rag.embedding_model = data.rag.embedding_model ?? ''
    rag.embedding_dim = Number(data.rag.embedding_dim ?? 512)
    rag.embedding_base_url = data.rag.embedding_base_url ?? ''
    rag.embedding_api_key = ''
    rag.has_embedding_key = !!data.rag.has_embedding_key
    rag.chunk_size = Number(data.rag.chunk_size ?? 400)
    rag.chunk_overlap = Number(data.rag.chunk_overlap ?? 60)
    rag.topk = Number(data.rag.topk ?? 5)
    rag.score_threshold = Number(data.rag.score_threshold ?? 0.5)
    rag.rerank = data.rag.rerank !== false
  }
  vectorBackend.value = data.vector_backend ?? rag.vector_backend
  kbDocuments.value = Number(data.kb_documents ?? 0)
  kbChunks.value = Number(data.kb_chunks ?? 0)
  docUploadReady.value = data.doc_upload_ready !== false
  docUploadReason.value = data.doc_upload_reason ?? ''
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    applySettings(await adminApi.getSettings())
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载系统设置失败'
  } finally {
    loading.value = false
  }
}

async function saveLlm() {
  savingLlm.value = true
  error.value = ''
  try {
    const payload = {
      base_url: llm.base_url.trim(),
      default_model: llm.default_model.trim(),
      temperature: Number(llm.temperature),
      max_tokens: Number(llm.max_tokens),
      ...(llm.api_key.trim() ? { api_key: llm.api_key.trim() } : {}),
    }
    await adminApi.saveLlm(payload)
    llm.api_key = ''
    notify('大模型配置已保存')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    savingLlm.value = false
  }
}

async function saveRag() {
  savingRag.value = true
  error.value = ''
  try {
    const res = await adminApi.saveRag({
      vector_backend: rag.vector_backend,
      vector_db_url: rag.vector_db_url.trim(),
      vector_hnsw_ef_search: Number(rag.vector_hnsw_ef_search),
      embedding_provider: rag.embedding_provider.trim(),
      embedding_model: rag.embedding_model.trim(),
      embedding_dim: Number(rag.embedding_dim),
      embedding_base_url: rag.embedding_base_url.trim(),
      ...(rag.embedding_api_key.trim() ? { embedding_api_key: rag.embedding_api_key.trim() } : {}),
      chunk_size: Number(rag.chunk_size),
      chunk_overlap: Number(rag.chunk_overlap),
      topk: Number(rag.topk),
      score_threshold: Number(rag.score_threshold),
      rerank: rag.rerank,
    })
    if (typeof res.kb_chunks === 'number') kbChunks.value = res.kb_chunks
    if (res.vector_backend) vectorBackend.value = res.vector_backend
    rag.embedding_api_key = ''
    notify(`向量与知识库配置已保存，索引重建完成（${kbChunks.value} 个分块，后端 ${vectorBackend.value}）`)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    savingRag.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="panel">
    <div v-if="error" class="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
    </div>
    <div v-if="flash" class="alert is-ok">
      <AppIcon name="check" :size="14" />
      <span>{{ flash }}</span>
    </div>

    <div class="kb-summary">
      <div class="kb-cell">
        <AppIcon name="book" :size="16" />
        <span class="kb-num">{{ kbDocuments }}</span>
        <span class="kb-label">知识文档</span>
      </div>
      <div class="kb-cell">
        <AppIcon name="layers" :size="16" />
        <span class="kb-num">{{ kbChunks }}</span>
        <span class="kb-label">向量分块</span>
      </div>
      <div class="kb-cell">
        <AppIcon name="database" :size="16" />
        <span class="kb-num is-text">{{ vectorBackend }}</span>
        <span class="kb-label">向量后端</span>
      </div>
    </div>

    <div v-if="loading" class="rows">
      <div class="skeleton" style="height: 220px" />
      <div class="skeleton" style="height: 320px" />
    </div>

    <template v-else>
      <section class="card block">
        <header class="block-head">
          <div>
            <h4><AppIcon name="cpu" :size="15" /> 大模型</h4>
            <p>配置对话模型服务，api_key 留空表示不修改。</p>
          </div>
        </header>
        <div class="form-grid">
          <label class="field col-span">
            <span class="field-label">base_url</span>
            <input v-model="llm.base_url" class="input" type="text" placeholder="https://api.example.com/v1" />
          </label>
          <label class="field col-span">
            <span class="field-label">api_key</span>
            <input v-model="llm.api_key" class="input" type="password" placeholder="留空表示不修改" autocomplete="off" />
          </label>
          <label class="field">
            <span class="field-label">default_model</span>
            <input v-model="llm.default_model" class="input" type="text" placeholder="deepseek-v4-flash" />
          </label>
          <label class="field">
            <span class="field-label">temperature</span>
            <input v-model="llm.temperature" class="input" type="number" step="0.1" min="0" max="2" />
          </label>
          <label class="field">
            <span class="field-label">max_tokens</span>
            <input v-model="llm.max_tokens" class="input" type="number" min="1" />
          </label>
        </div>
        <div class="block-foot">
          <button class="btn btn-primary btn-sm" type="button" :disabled="savingLlm" @click="saveLlm">
            <span v-if="savingLlm" class="spinner" />
            保存大模型配置
          </button>
        </div>
      </section>

      <section class="card block">
        <header class="block-head">
          <div>
            <h4><AppIcon name="database" :size="15" /> 向量库与 Embedding 模型</h4>
            <p>向量后端可选 pgvector（PostgreSQL 生产形态）或 memory；保存后自动重建索引。</p>
          </div>
        </header>

        <div v-if="!docUploadReady" class="doc-gate">
          <AppIcon name="alert" :size="14" />
          <span>知识文档上传当前不可用：{{ docUploadReason || '向量模型未配置' }}</span>
        </div>
        <p v-else class="doc-ready">
          <AppIcon name="check" :size="13" />
          知识文档上传已开放：用户可在规划页「＋ → 上传文档到知识库」上传 pdf / wps(docx) / txt / md，
          解析清洗后写入当前向量库（{{ vectorBackend }} · {{ kbChunks }} 个分块）。
        </p>
        <div class="form-grid">
          <label class="field">
            <span class="field-label">向量后端 vector_backend</span>
            <select v-model="rag.vector_backend" class="input">
              <option value="memory">memory（内存，零依赖）</option>
              <option value="pgvector">pgvector（PostgreSQL + HNSW）</option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">HNSW ef_search</span>
            <input v-model="rag.vector_hnsw_ef_search" class="input" type="number" min="10" max="512" />
          </label>
          <label class="field col-span">
            <span class="field-label">vector_db_url</span>
            <input v-model="rag.vector_db_url" class="input" type="text" placeholder="postgresql://postgres:postgres@127.0.0.1:5432/travelvec" />
          </label>
          <label class="field">
            <span class="field-label">embedding_provider</span>
            <select v-model="rag.embedding_provider" class="input">
              <option value="hash">hash（离线确定性）</option>
              <option value="openai">openai（真实向量模型）</option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">embedding_model</span>
            <input v-model="rag.embedding_model" class="input" type="text" placeholder="text-embedding-3-small" />
          </label>
          <label class="field">
            <span class="field-label">embedding_dim</span>
            <input v-model="rag.embedding_dim" class="input" type="number" min="64" max="3072" />
          </label>
          <label class="field">
            <span class="field-label">embedding_base_url</span>
            <input v-model="rag.embedding_base_url" class="input" type="text" placeholder="留空复用大模型 base_url" />
          </label>
          <label class="field col-span">
            <span class="field-label">embedding_api_key</span>
            <input
              v-model="rag.embedding_api_key"
              class="input"
              type="password"
              autocomplete="off"
              :placeholder="rag.has_embedding_key ? '已配置，留空表示不修改' : 'provider=openai 时填写'"
            />
          </label>
        </div>
        <div class="form-grid" style="margin-top: 12px">
          <label class="field">
            <span class="field-label">chunk_size</span>
            <input v-model="rag.chunk_size" class="input" type="number" min="64" />
          </label>
          <label class="field">
            <span class="field-label">chunk_overlap</span>
            <input v-model="rag.chunk_overlap" class="input" type="number" min="0" />
          </label>
          <label class="field">
            <span class="field-label">topk</span>
            <input v-model="rag.topk" class="input" type="number" min="1" />
          </label>
          <label class="field">
            <span class="field-label">score_threshold</span>
            <input v-model="rag.score_threshold" class="input" type="number" step="0.01" min="0" max="1" />
          </label>
          <label class="field">
            <span class="field-label">rerank 精排</span>
            <select v-model="rag.rerank" class="input">
              <option :value="true">开启（查询改写+词法重排）</option>
              <option :value="false">关闭</option>
            </select>
          </label>
        </div>
        <p class="balance-tip">
          <AppIcon name="info" :size="13" />
          参数均衡：temperature 低（0.2~0.3）减少幻觉、topk 取 5 兼顾召回与上下文占用、阈值过滤弱相关块。
        </p>
        <div class="block-foot">
          <button class="btn btn-primary btn-sm" type="button" :disabled="savingRag" @click="saveRag">
            <span v-if="savingRag" class="spinner" />
            保存并重建索引
          </button>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.alert {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 13px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.alert.is-ok {
  background: var(--success-soft);
  color: var(--success);
}

.kb-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.kb-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid var(--border);
  color: var(--primary-strong);
}

.kb-num {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
}

.kb-num.is-text {
  font-size: 15px;
}

.kb-label {
  font-size: 12.5px;
  color: var(--text-muted);
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.block {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.block-head h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14.5px;
  font-weight: 650;
}

.block-head p {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.col-span {
  grid-column: span 2;
}

.doc-gate {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 12.5px;
}

.doc-ready {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--success-soft);
  color: var(--success);
  font-size: 12.5px;
  line-height: 1.7;
}

.balance-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--panel-soft);
  border: 1px dashed var(--border);
  border-radius: 9px;
  padding: 8px 11px;
}

.block-foot {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 680px) {
  .form-grid,
  .kb-summary {
    grid-template-columns: 1fr;
  }

  .col-span {
    grid-column: auto;
  }
}
</style>
