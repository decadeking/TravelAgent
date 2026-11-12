<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import AppModal from '@/components/AppModal.vue'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/http'
import { mediaApi } from '@/api/media'
import type { KbDoc, KbSearchHit, McpStatus, RagSelfTestResult } from '@/types'

const docs = ref<KbDoc[]>([])
const loading = ref(true)
const error = ref('')
const flash = ref('')
const busyId = ref<number | null>(null)
const reindexing = ref(false)

const selftest = ref<RagSelfTestResult | null>(null)
const testing = ref(false)
const mcp = ref<McpStatus | null>(null)

const docInput = ref<HTMLInputElement | null>(null)
const uploadingDoc = ref(false)

const showAdd = ref(false)
const saving = ref(false)
const form = reactive({ city: '', title: '', content: '', source: '' })

const query = ref('')
const city = ref('')
const searching = ref(false)
const hits = ref<KbSearchHit[] | null>(null)

function notify(text: string) {
  flash.value = text
  window.setTimeout(() => {
    flash.value = ''
  }, 3000)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    docs.value = await adminApi.kb()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载知识库失败'
  } finally {
    loading.value = false
  }
}

function openAdd() {
  form.city = ''
  form.title = ''
  form.content = ''
  form.source = ''
  showAdd.value = true
}

async function submitAdd() {
  if (!form.city.trim() || !form.title.trim() || !form.content.trim()) {
    error.value = '城市、标题与内容不能为空'
    return
  }
  saving.value = true
  error.value = ''
  try {
    await adminApi.addKb({
      city: form.city.trim(),
      title: form.title.trim(),
      content: form.content.trim(),
      source: form.source.trim(),
    })
    showAdd.value = false
    await load()
    notify('知识文档已新增并完成索引')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '新增失败'
  } finally {
    saving.value = false
  }
}

async function removeDoc(doc: KbDoc) {
  if (!window.confirm(`确认删除知识文档「${doc.title}」？`)) return
  busyId.value = doc.id
  try {
    await adminApi.removeKb(doc.id)
    await load()
    notify('已删除该知识文档')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  } finally {
    busyId.value = null
  }
}

async function reindex() {
  reindexing.value = true
  error.value = ''
  try {
    const res = await adminApi.reindex()
    notify(`索引重建完成，共 ${res.kb_chunks ?? 0} 个分块`)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '重建索引失败'
  } finally {
    reindexing.value = false
  }
}

async function search() {
  if (!query.value.trim()) return
  searching.value = true
  error.value = ''
  try {
    hits.value = await adminApi.search(query.value.trim(), city.value.trim())
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '检索失败'
  } finally {
    searching.value = false
  }
}

/** RAG 全链路自检：内置测试 txt → 清洗 / 切片 / 向量化 / 入库 / 检索 */
async function runSelfTest() {
  testing.value = true
  error.value = ''
  try {
    selftest.value = await adminApi.kbSelfTest()
    notify(selftest.value.passed ? 'RAG 全链路自检通过' : '自检未全部通过，请查看各环节结果')
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '自检失败'
  } finally {
    testing.value = false
  }
}

function stageSummary(detail: Record<string, unknown>): string {
  if (!detail) return ''
  if (detail.backend) {
    return `后端 ${detail.backend} · 入库 ${detail.store_size} 块`
  }
  if (detail.chunks !== undefined && detail.chunk_size !== undefined) {
    return `切片 ${detail.chunks} 块（块 ${detail.chunk_size} / 重叠 ${detail.overlap}）`
  }
  if (detail.provider !== undefined) {
    return `${detail.provider} · ${detail.model} · ${detail.dim} 维`
  }
  if (detail.clean_chars !== undefined) {
    return `原始 ${detail.raw_chars} 字 → 清洗后 ${detail.clean_chars} 字，剔除 ${detail.dropped_lines} 行`
  }
  if (detail.hits !== undefined) {
    return `命中 ${detail.hits} 条（阈值 ${detail.score_threshold}）`
  }
  return JSON.stringify(detail)
}

/** 上传知识文档（pdf / wps(docx) / txt / md）→ 解析清洗 → 入 RAG 知识库 */
async function onDocUpload(event: Event) {
  const el = event.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  uploadingDoc.value = true
  error.value = ''
  try {
    const res = await mediaApi.uploadDoc(file)
    notify(`已入库：${res.title}（清洗 ${res.clean.clean_chars} 字 · 切片 ${res.chunks} 块 · 总量 ${res.total_chunks} · ${res.vector_backend}）`)
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '文档上传失败'
  } finally {
    uploadingDoc.value = false
  }
}

onMounted(async () => {
  await load()
  try {
    mcp.value = await adminApi.mcpStatus()
  } catch {
    /* 非管理员或 MCP 不可用时忽略 */
  }
})
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

    <section class="card block">
      <header class="block-head">
        <div>
          <h4><AppIcon name="sparkle" :size="15" /> RAG 全链路自检</h4>
          <p>用内置测试文档走完「原料清洗 → 切片 → 向量化 → 入库 → 检索」，逐步给出判定。</p>
        </div>
        <div class="head-actions">
          <button class="btn btn-primary btn-sm" type="button" :disabled="testing" @click="runSelfTest">
            <span v-if="testing" class="spinner" />
            <AppIcon v-else name="check" :size="14" />
            运行自检
          </button>
        </div>
      </header>

      <div v-if="mcp" class="mcp-strip">
        <span class="tag" :class="mcp.status === 'ready' ? 'tag-ok' : 'tag-soft'">
          MCP {{ mcp.status }}
        </span>
        <span class="mcp-text">
          {{ mcp.transport }} · 工具 {{ mcp.counts.tools }} 个 · 调用 {{ mcp.counts.calls }} 次 ·
          健康检查 {{ mcp.counts.checks }} 次 · 重连 {{ mcp.counts.reloads }} 次
        </span>
      </div>

      <div v-if="selftest" class="selftest">
        <div class="verdict" :class="{ 'is-ok': selftest.passed }">
          <AppIcon :name="selftest.passed ? 'check' : 'alert'" :size="15" />
          <span>
            {{ selftest.passed ? '全部环节有效' : '存在未通过环节' }} ·
            向量库 {{ selftest.vector_backend }} · 向量模型 {{ selftest.embedding_provider }} ·
            总块数 {{ selftest.total_chunks }}
          </span>
        </div>
        <div class="stages">
          <div v-for="st in selftest.stages" :key="st.name" class="stage" :class="{ 'is-ok': st.ok }">
            <AppIcon :name="st.ok ? 'check' : 'alert'" :size="14" />
            <div class="stage-main">
              <span class="stage-name">{{ st.name }}</span>
              <span class="stage-detail">{{ stageSummary(st.detail) }}</span>
            </div>
          </div>
        </div>
        <p class="sample-text">样本 {{ selftest.sample.file }}（{{ selftest.sample.chars }} 字）：{{ selftest.sample.preview }}…</p>
      </div>
      <p v-else class="empty-tip">点击「运行自检」验证当前知识库的清洗、切片、向量化与检索链路。</p>
    </section>

    <section class="card block">
      <header class="block-head">
        <div>
          <h4><AppIcon name="search" :size="15" /> 检索测试</h4>
          <p>输入问题，验证 RAG 是否能命中知识库分块。</p>
        </div>
      </header>
      <div class="search-row">
        <input v-model="city" class="input city-input" type="text" placeholder="城市（可选）" />
        <input
          v-model="query"
          class="input"
          type="text"
          placeholder="如：成都适合亲子的景点有哪些"
          @keydown.enter="search"
        />
        <button class="btn btn-primary" type="button" :disabled="searching || !query.trim()" @click="search">
          <span v-if="searching" class="spinner" />
          检索
        </button>
      </div>

      <div v-if="hits" class="hits">
        <p v-if="!hits.length" class="empty-tip">未命中任何分块。</p>
        <div v-for="hit in hits" :key="hit.chunk_id" class="hit">
          <div class="hit-head">
            <span class="hit-title">{{ hit.title || hit.city || '知识片段' }}</span>
            <span class="hit-score">分数 {{ (hit.score ?? 0).toFixed(3) }}</span>
          </div>
          <p class="hit-text">{{ hit.text }}</p>
        </div>
      </div>
    </section>

    <section class="card block">
      <header class="block-head">
        <div>
          <h4><AppIcon name="book" :size="15" /> 知识文档</h4>
          <p>共 {{ docs.length }} 篇，新增或删除后会自动重建索引。</p>
        </div>
        <div class="head-actions">
          <button class="btn btn-ghost btn-sm" type="button" :disabled="reindexing" @click="reindex">
            <span v-if="reindexing" class="spinner spinner-dark" />
            <AppIcon v-else name="refresh" :size="14" />
            重建索引
          </button>
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :disabled="uploadingDoc"
            @click="docInput?.click()"
          >
            <span v-if="uploadingDoc" class="spinner spinner-dark" />
            <AppIcon v-else name="upload" :size="14" />
            {{ uploadingDoc ? '上传中…' : '上传文档' }}
          </button>
          <button class="btn btn-primary btn-sm" type="button" @click="openAdd">
            <AppIcon name="plus" :size="14" />
            新增文档
          </button>
        </div>
      </header>

      <input
        ref="docInput"
        type="file"
        accept=".pdf,.docx,.txt,.md"
        class="hidden-file"
        @change="onDocUpload"
      />

      <div v-if="loading" class="rows">
        <div v-for="i in 3" :key="i" class="skeleton" style="height: 56px" />
      </div>
      <p v-else-if="!docs.length" class="empty-tip">知识库为空，先添加一篇文档试试。</p>
      <div v-else class="rows">
        <article v-for="doc in docs" :key="doc.id" class="doc">
          <div class="doc-main">
            <div class="doc-title">
              <span class="tag tag-soft">{{ doc.city || '通用' }}</span>
              <span class="doc-name">{{ doc.title }}</span>
            </div>
            <p class="doc-text">{{ doc.content }}</p>
            <p v-if="doc.source" class="doc-source">来源：{{ doc.source }}</p>
          </div>
          <button class="btn btn-danger btn-sm" type="button" :disabled="busyId === doc.id" @click="removeDoc(doc)">
            <AppIcon name="trash" :size="14" />
            删除
          </button>
        </article>
      </div>
    </section>

    <AppModal v-if="showAdd" title="新增知识文档" subtitle="内容将按配置分块并写入向量索引" wide @close="showAdd = false">
      <div class="form">
        <div class="row-2">
          <label class="field">
            <span class="field-label">城市</span>
            <input v-model="form.city" class="input" type="text" placeholder="如 成都" />
          </label>
          <label class="field">
            <span class="field-label">来源（可选）</span>
            <input v-model="form.source" class="input" type="text" placeholder="如 官方攻略" />
          </label>
        </div>
        <label class="field">
          <span class="field-label">标题</span>
          <input v-model="form.title" class="input" type="text" placeholder="文档标题" />
        </label>
        <label class="field">
          <span class="field-label">内容</span>
          <textarea v-model="form.content" class="textarea" rows="6" placeholder="粘贴攻略、景点介绍或注意事项…" />
        </label>
      </div>
      <template #footer>
        <button class="btn btn-ghost" type="button" @click="showAdd = false">取消</button>
        <button class="btn btn-primary" type="button" :disabled="saving" @click="submitAdd">
          <span v-if="saving" class="spinner" />
          保存并索引
        </button>
      </template>
    </AppModal>
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

.block {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.block-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
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

.head-actions {
  display: flex;
  gap: 8px;
}

.hidden-file {
  display: none;
}

.mcp-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 9px;
  background: var(--panel-soft);
  border: 1px solid var(--border-soft);
}

.mcp-text {
  font-size: 12px;
  color: var(--text-muted);
}

.tag-ok {
  background: var(--success-soft);
  color: var(--success);
}

.selftest {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.verdict {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.verdict.is-ok {
  background: var(--success-soft);
  color: var(--success);
}

.stages {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stage {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 7px 10px;
  border-radius: 8px;
  background: #fafbfc;
  border: 1px solid var(--border-soft);
  color: var(--danger);
}

.stage.is-ok {
  color: var(--success);
}

.stage-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.stage-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}

.stage-detail {
  font-size: 11.5px;
  color: var(--text-muted);
}

.sample-text {
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--text-faint);
}

.search-row {
  display: flex;
  gap: 10px;
}

.city-input {
  width: 140px;
  flex-shrink: 0;
}

.hits {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hit {
  padding: 11px 13px;
  border-left: 3px solid var(--primary);
  border-radius: 8px;
  background: var(--panel-soft);
}

.hit-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.hit-title {
  font-size: 13px;
  font-weight: 600;
}

.hit-score {
  font-size: 11.5px;
  color: var(--text-faint);
}

.hit-text {
  margin-top: 5px;
  font-size: 12.5px;
  color: var(--text-muted);
  line-height: 1.7;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.doc {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
}

.doc-main {
  flex: 1;
  min-width: 0;
}

.doc-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.doc-name {
  font-size: 13.5px;
  font-weight: 600;
}

.doc-text {
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--text-muted);
  line-height: 1.65;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.doc-source {
  margin-top: 5px;
  font-size: 11.5px;
  color: var(--text-faint);
}

.empty-tip {
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--text-faint);
}

.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

@media (max-width: 680px) {
  .search-row {
    flex-wrap: wrap;
  }

  .city-input {
    width: 100%;
  }

  .row-2 {
    grid-template-columns: 1fr;
  }
}
</style>
