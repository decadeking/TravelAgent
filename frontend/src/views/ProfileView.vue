<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { agentApi } from '@/api/agent'
import { ApiError } from '@/api/http'
import { knowledgeApi } from '@/api/knowledge'
import { mediaApi } from '@/api/media'
import { userApi } from '@/api/users'
import { formatDateTime } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import type { AgentModel, KnowledgeOverview, SessionSummary } from '@/types'

interface PrefRow {
  key: string
  value: string
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()

const prefs = ref<PrefRow[]>([])
const sessions = ref<SessionSummary[]>([])
const models = ref<AgentModel[]>([])
const hasApiKey = ref(true)
const hasOwnKey = ref(false)
const apiKeyInput = ref('')
const savingModel = ref(false)
const testingModel = ref(false)
const testResult = ref<{ ok: boolean; message: string } | null>(null)
const uploadingAvatar = ref(false)

const loadingPrefs = ref(true)
const loadingSessions = ref(true)
const loadingModels = ref(true)
const loadingKnowledge = ref(true)
const knowledge = ref<KnowledgeOverview | null>(null)
const savingPrefs = ref(false)
const savingProfile = ref(false)
const error = ref('')
const flash = ref('')

// ---- 个人资料 ----
const nickname = ref('')
const bio = ref('')
const avatarDraft = ref('')

const PRESETS: Array<[string, string]> = [
  ['#6366f1', '#3b82f6'],
  ['#0ea5e9', '#22c55e'],
  ['#f59e0b', '#ef4444'],
  ['#8b5cf6', '#ec4899'],
  ['#14b8a6', '#0ea5e9'],
  ['#f43f5e', '#f97316'],
]

const user = computed(() => auth.user)
const avatarPreview = computed(() => (avatarDraft.value || '').trim())

const currentModelId = computed(() => ui.preferredModel || models.value[0]?.id || '')

function notify(text: string) {
  flash.value = text
  window.setTimeout(() => {
    flash.value = ''
  }, 3000)
}

function presetAvatar(index: number): string {
  const [c1, c2] = PRESETS[index]
  const initial = (nickname.value || auth.displayName || '旅').trim().slice(0, 1).toUpperCase()
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs><rect width="96" height="96" rx="30" fill="url(#g)"/><text x="48" y="63" font-size="42" fill="#ffffff" text-anchor="middle" font-family="system-ui,sans-serif">${initial}</text></svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

function pickPreset(index: number) {
  avatarDraft.value = presetAvatar(index)
}

async function onFileChange(event: Event) {
  const el = event.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  uploadingAvatar.value = true
  error.value = ''
  try {
    const res = await mediaApi.upload(file, 'avatar')
    avatarDraft.value = res.url
    notify('头像已上传，记得点击「保存资料」')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '头像上传失败'
  } finally {
    uploadingAvatar.value = false
  }
}

async function saveProfile() {
  if (!nickname.value.trim()) {
    error.value = '昵称不能为空'
    return
  }
  savingProfile.value = true
  error.value = ''
  try {
    const updated = await userApi.updateMe({
      nickname: nickname.value.trim(),
      avatar: avatarDraft.value.trim(),
      bio: bio.value.trim(),
    })
    auth.setUser(updated)
    notify('资料已保存')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存资料失败'
  } finally {
    savingProfile.value = false
  }
}

// ---- 模型配置 ----
async function selectModel(id: string) {
  ui.setPreferredModel(id)
  try {
    await userApi.saveModelConfig({ model: id })
    notify('已保存默认模型')
  } catch {
    notify('已切换默认模型偏好')
  }
}

async function saveModelKey() {
  savingModel.value = true
  error.value = ''
  testResult.value = null
  try {
    const res = await userApi.saveModelConfig({
      api_key: apiKeyInput.value.trim(),
      model: currentModelId.value,
    })
    hasApiKey.value = res.has_api_key
    hasOwnKey.value = res.has_api_key
    apiKeyInput.value = ''
    notify(res.has_api_key ? '密钥已保存，将使用真实大模型' : '未填写密钥，继续使用离线模拟')
    // 保存后自动测试一次，把真实连通结果反馈给用户
    await testModelConfig()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存模型配置失败'
  } finally {
    savingModel.value = false
  }
}

async function testModelConfig() {
  testingModel.value = true
  testResult.value = null
  try {
    const res = await userApi.testModelConfig({
      api_key: apiKeyInput.value.trim() || undefined,
      model: currentModelId.value || undefined,
    })
    const message =
      res.model_used && !res.message.includes(res.model_used)
        ? `${res.message}（实际使用模型：${res.model_used}）`
        : res.message
    testResult.value = { ok: res.ok, message }
  } catch (err) {
    testResult.value = { ok: false, message: err instanceof ApiError ? err.message : '测试连接失败' }
  } finally {
    testingModel.value = false
  }
}

async function clearModelKey() {
  try {
    const res = await userApi.saveModelConfig({ clear_api_key: true })
    hasApiKey.value = res.has_api_key
    hasOwnKey.value = res.has_api_key
    apiKeyInput.value = ''
    testResult.value = null
    notify('已清除密钥，将使用离线模拟')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '清除密钥失败'
  }
}

// ---- 知识库概览 ----
async function loadKnowledge() {
  loadingKnowledge.value = true
  try {
    knowledge.value = await knowledgeApi.overview(8)
  } catch {
    knowledge.value = null      // 概览失败时展示占位提示，不影响其它区块
  } finally {
    loadingKnowledge.value = false
  }
}

// ---- 偏好 ----
async function loadPrefs() {
  loadingPrefs.value = true
  try {
    const data = await userApi.getPreferences()
    prefs.value = Object.entries(data).map(([key, value]) => ({ key, value: String(value) }))
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载偏好失败'
  } finally {
    loadingPrefs.value = false
  }
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    sessions.value = await agentApi.sessions()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载会话失败'
  } finally {
    loadingSessions.value = false
  }
}

async function loadModels() {
  loadingModels.value = true
  try {
    const res = await userApi.getModelConfig()
    models.value = res.models ?? []
    hasApiKey.value = res.has_api_key
    hasOwnKey.value = res.has_own_api_key
    if (res.selected_model) ui.setPreferredModel(res.selected_model)
  } catch {
    /* 忽略 */
  } finally {
    loadingModels.value = false
  }
}

function addPref() {
  prefs.value.push({ key: '', value: '' })
}

function removePref(index: number) {
  prefs.value.splice(index, 1)
}

async function savePrefs() {
  error.value = ''
  const payload: Record<string, string> = {}
  for (const row of prefs.value) {
    const key = row.key.trim()
    if (!key) continue
    if (key in payload) {
      error.value = `偏好键「${key}」重复`
      return
    }
    payload[key] = row.value.trim()
  }
  savingPrefs.value = true
  try {
    const saved = await userApi.savePreferences(payload)
    prefs.value = Object.entries(saved).map(([key, value]) => ({ key, value: String(value) }))
    notify('偏好已保存，将在后续规划中生效')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    savingPrefs.value = false
  }
}

function openSession(session: SessionSummary) {
  router.push({ name: 'plan', query: { session: session.session_id } })
}

function scrollToHash(hash: string) {
  if (!hash) return
  const el = document.querySelector(hash)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(
  () => route.hash,
  (hash) => scrollToHash(hash),
)

watch(
  () => auth.user,
  (value) => {
    if (!value) return
    if (!nickname.value) nickname.value = value.nickname ?? ''
    if (!bio.value) bio.value = value.bio ?? ''
    if (!avatarDraft.value) avatarDraft.value = value.avatar ?? ''
  },
  { immediate: true },
)

onMounted(() => {
  if (!auth.user) {
    auth.fetchMe().catch(() => {})
  }
  nickname.value = auth.user?.nickname ?? ''
  bio.value = auth.user?.bio ?? ''
  avatarDraft.value = auth.user?.avatar ?? ''
  loadPrefs()
  loadSessions()
  loadModels()
  loadKnowledge()
  window.setTimeout(() => scrollToHash(route.hash), 200)
})
</script>

<template>
  <div class="profile">
    <div v-if="error" class="flash is-error">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
    </div>
    <div v-if="flash" class="flash">
      <AppIcon name="check" :size="14" />
      <span>{{ flash }}</span>
    </div>

    <!-- 头像与资料 -->
    <section id="profile" class="card section">
      <header class="section-head">
        <div>
          <h2>头像与资料</h2>
          <span class="muted">自定义头像与个人简介，修改后右上角头像会立即更新</span>
        </div>
        <button class="btn btn-primary btn-sm" type="button" :disabled="savingProfile" @click="saveProfile">
          <span v-if="savingProfile" class="spinner" />
          保存资料
        </button>
      </header>

      <div class="profile-edit">
        <div class="avatar-col">
          <UserAvatar :src="avatarPreview" :name="nickname || auth.displayName" :size="76" :radius="24" />
          <label class="btn btn-ghost btn-sm upload-btn" :class="{ 'is-busy': uploadingAvatar }">
            <span v-if="uploadingAvatar" class="spinner spinner-dark" />
            <AppIcon v-else name="upload" :size="14" />
            {{ uploadingAvatar ? '上传中…' : '上传图片' }}
            <input type="file" accept="image/*" class="file-input" :disabled="uploadingAvatar" @change="onFileChange" />
          </label>
        </div>

        <div class="avatar-options">
          <div class="option-block">
            <span class="option-label"><AppIcon name="link" :size="13" /> 图片链接</span>
            <input v-model="avatarDraft" class="input" type="text" placeholder="https://example.com/avatar.jpg" />
          </div>
          <div class="option-block">
            <span class="option-label"><AppIcon name="palette" :size="13" /> 预设头像</span>
            <div class="presets">
              <button
                v-for="(_, index) in PRESETS"
                :key="index"
                class="preset"
                type="button"
                :style="{ background: `linear-gradient(135deg, ${PRESETS[index][0]}, ${PRESETS[index][1]})` }"
                @click="pickPreset(index)"
              />
              <button class="preset preset-clear" type="button" title="清除自定义头像" @click="avatarDraft = ''">
                <AppIcon name="close" :size="14" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="form-grid">
        <label class="field">
          <span class="field-label">昵称</span>
          <input v-model="nickname" class="input" type="text" placeholder="想让我们怎么称呼你" />
        </label>
        <label class="field">
          <span class="field-label">用户名</span>
          <input class="input" type="text" :value="user?.username || '-'" disabled />
        </label>
        <label class="field col-span">
          <span class="field-label">个人简介</span>
          <textarea v-model="bio" class="textarea" rows="2" placeholder="一句话介绍自己，如：热爱人文与美食的旅行者" />
        </label>
      </div>
    </section>

    <!-- 模型配置 -->
    <section id="model" class="card section">
      <header class="section-head">
        <div>
          <h2>模型配置</h2>
          <span class="muted">选择模型并填入你自己的 API Key，即可使用真实大模型（其余为固定配置）</span>
        </div>
      </header>

      <div v-if="!hasApiKey" class="hint-strip">
        <AppIcon name="info" :size="14" />
        还没配置密钥，规划将使用离线模拟输出；填入自己的 API Key 后即可调用真实模型。
      </div>
      <div v-else class="hint-strip is-ok">
        <AppIcon name="check" :size="14" />
        已配置 API Key，规划将调用真实大模型；可点击「测试连接」验证可用性。
      </div>

      <div v-if="loadingModels" class="pref-list">
        <div v-for="i in 2" :key="i" class="skeleton" style="height: 52px" />
      </div>

      <div v-else-if="!models.length" class="pref-empty">
        <p class="muted">暂无可选模型。</p>
      </div>

      <ul v-else class="model-list">
        <li
          v-for="model in models"
          :key="model.id"
          class="model-row"
          :class="{ 'is-active': model.id === currentModelId }"
          @click="selectModel(model.id)"
        >
          <div class="model-row-main">
            <span class="model-row-name">{{ model.name }}</span>
            <span class="model-row-desc">{{ model.description || model.provider }}</span>
          </div>
          <span class="model-radio">
            <AppIcon v-if="model.id === currentModelId" name="check" :size="14" />
          </span>
        </li>
      </ul>

      <div class="key-block">
        <label class="field key-field">
          <span class="field-label">API Key</span>
          <input
            v-model="apiKeyInput"
            class="input"
            type="password"
            autocomplete="off"
            :placeholder="hasOwnKey ? '已配置，留空表示不修改' : '填入你的 API Key，例如 sk-...'"
          />
        </label>
        <button class="btn btn-primary btn-sm" type="button" :disabled="savingModel" @click="saveModelKey">
          <span v-if="savingModel" class="spinner" />
          保存配置
        </button>
        <button class="btn btn-ghost btn-sm" type="button" :disabled="testingModel" @click="testModelConfig">
          <span v-if="testingModel" class="spinner spinner-dark" />
          {{ testingModel ? '测试中…' : '测试连接' }}
        </button>
        <button v-if="hasOwnKey" class="btn btn-ghost btn-sm" type="button" @click="clearModelKey">
          清除密钥
        </button>
      </div>

      <div v-if="testResult" class="test-result" :class="testResult.ok ? 'is-ok' : 'is-error'">
        <AppIcon :name="testResult.ok ? 'check' : 'alert'" :size="14" />
        <span>{{ testResult.message }}</span>
      </div>
    </section>

    <!-- RAG 知识库概览（替代原「已迁移到消息」入口） -->
    <section id="knowledge" class="card section">
      <header class="section-head">
        <div>
          <h2>RAG 知识库</h2>
          <span class="muted">
            智能体规划时会从知识库检索攻略与事实依据，资料越全，行程越准。
          </span>
        </div>
        <button class="btn btn-primary btn-sm" type="button" @click="router.push({ name: 'plan' })">
          <AppIcon name="upload" :size="14" />
          去上传文档
        </button>
      </header>

      <div v-if="loadingKnowledge" class="kb-stats">
        <div v-for="i in 4" :key="i" class="skeleton" style="height: 62px" />
      </div>

      <template v-else-if="knowledge">
        <div v-if="!knowledge.ready" class="kb-notice">
          <AppIcon name="alert" :size="14" />
          <span>{{ knowledge.reason || '知识库暂未开放' }}</span>
        </div>

        <div class="kb-stats">
          <div class="kb-stat">
            <span class="kb-stat-label">向量库后端</span>
            <span class="kb-stat-value">{{ knowledge.vector_backend }}</span>
          </div>
          <div class="kb-stat">
            <span class="kb-stat-label">知识文档</span>
            <span class="kb-stat-value">{{ knowledge.documents }} 篇</span>
          </div>
          <div class="kb-stat">
            <span class="kb-stat-label">向量分块</span>
            <span class="kb-stat-value">{{ knowledge.chunks }} 块</span>
          </div>
          <div class="kb-stat">
            <span class="kb-stat-label">向量模型</span>
            <span class="kb-stat-value">
              {{ knowledge.embedding.provider }} · {{ knowledge.embedding.dim }} 维
            </span>
          </div>
        </div>

        <dl class="kb-meta">
          <div><dt>切片策略</dt><dd>每块 {{ knowledge.chunking.size }} 字 · 重叠 {{ knowledge.chunking.overlap }} 字</dd></div>
          <div><dt>检索配置</dt><dd>Top {{ knowledge.retrieval.topk }} · 相似度阈值 {{ knowledge.retrieval.threshold }} · {{ knowledge.retrieval.rerank ? '词法+向量混合精排' : '仅向量检索' }}</dd></div>
          <div><dt>嵌入模型</dt><dd>{{ knowledge.embedding.model || '—' }}</dd></div>
        </dl>

        <div class="kb-docs">
          <div class="kb-docs-head">
            <span>最近入库文档</span>
            <span class="muted">{{ knowledge.recent.length }} / {{ knowledge.documents }}</span>
          </div>
          <p v-if="!knowledge.recent.length" class="muted kb-empty">
            知识库还是空的，去规划页通过输入框左侧「＋ → 上传文档到知识库」上传 pdf / wps / txt 试试。
          </p>
          <ul v-else class="kb-doc-list">
            <li v-for="doc in knowledge.recent" :key="doc.id" class="kb-doc">
              <span class="kb-doc-city">{{ doc.city }}</span>
              <span class="kb-doc-title" :title="doc.title">{{ doc.title }}</span>
              <span class="kb-doc-chars">{{ doc.chars }} 字</span>
            </li>
          </ul>
        </div>
      </template>

      <p v-else class="muted">知识库信息暂不可用，请稍后再试。</p>
    </section>

    <!-- 偏好管理 -->
    <section id="preferences" class="card section">
      <header class="section-head">
        <div>
          <h2>偏好管理</h2>
          <span class="muted">长期记忆，规划时会自动参考（例如 prefer=亲子、avoid=登山）</span>
        </div>
        <button class="btn btn-ghost btn-sm" type="button" @click="addPref">
          <AppIcon name="plus" :size="14" />
          新增偏好
        </button>
      </header>

      <div v-if="loadingPrefs" class="pref-list">
        <div v-for="i in 3" :key="i" class="skeleton" style="height: 40px" />
      </div>

      <div v-else-if="!prefs.length" class="pref-empty">
        <p class="muted">还没有偏好设置，添加一条试试，例如「旅行节奏 = 轻松」。</p>
      </div>

      <div v-else class="pref-list">
        <div v-for="(row, index) in prefs" :key="index" class="pref-row">
          <input v-model="row.key" class="input" placeholder="偏好名称，如 pace" />
          <input v-model="row.value" class="input" placeholder="偏好值，如 轻松" />
          <button class="btn btn-quiet btn-sm" type="button" title="删除" @click="removePref(index)">
            <AppIcon name="trash" :size="15" />
          </button>
        </div>
      </div>

      <div class="section-foot">
        <button class="btn btn-primary btn-sm" type="button" :disabled="savingPrefs" @click="savePrefs">
          <span v-if="savingPrefs" class="spinner" />
          保存偏好
        </button>
      </div>
    </section>

    <!-- 历史会话 -->
    <section id="sessions" class="card section">
      <header class="section-head">
        <h2>历史会话</h2>
        <span class="muted">点击可恢复上下文继续规划</span>
      </header>

      <div v-if="loadingSessions" class="session-list">
        <div v-for="i in 3" :key="i" class="skeleton" style="height: 52px" />
      </div>

      <EmptyState
        v-else-if="!sessions.length"
        title="暂无历史会话"
        description="去规划页和智能体聊一聊，会话会自动保存到这里。"
        action-text="开始规划"
        @action="router.push({ name: 'plan' })"
      />

      <ul v-else class="session-list">
        <li v-for="session in sessions" :key="session.session_id" class="session-item">
          <div class="session-main">
            <div class="session-summary">{{ session.summary || '（无摘要）' }}</div>
            <div class="session-meta">
              <span class="session-id">{{ session.session_id }}</span>
              <span class="meta-sep">·</span>
              <span>{{ formatDateTime(session.created_at) }}</span>
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="openSession(session)">
            <AppIcon name="chevron-right" :size="14" />
            恢复会话
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.profile {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 860px;
  margin: 0 auto;
}

.flash {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--success-soft);
  color: var(--success);
  font-size: 12.5px;
}

.flash.is-error {
  background: var(--danger-soft);
  color: var(--danger);
}

.section {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  scroll-margin-top: 84px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.section-head h2 {
  font-size: 15px;
  font-weight: 600;
}

.section-head .muted {
  display: block;
  margin-top: 4px;
  font-size: 12.5px;
}

.section-foot {
  display: flex;
  justify-content: flex-end;
}

.count-badge {
  display: inline-grid;
  place-items: center;
  min-width: 26px;
  height: 26px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary-strong);
  font-size: 12.5px;
  font-weight: 600;
}

/* ---- RAG 知识库概览 ---- */
.kb-notice {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 12.5px;
}

.kb-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.kb-stat {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 12px 14px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--panel-soft);
}

.kb-stat-label {
  font-size: 11.5px;
  color: var(--text-faint);
}

.kb-stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.kb-meta {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px 14px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: #fafbfc;
}

.kb-meta > div {
  display: flex;
  gap: 10px;
  font-size: 12.5px;
  line-height: 1.6;
}

.kb-meta dt {
  flex: 0 0 72px;
  color: var(--text-faint);
}

.kb-meta dd {
  color: var(--text-muted);
}

.kb-docs {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.kb-docs-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}

.kb-empty {
  font-size: 12.5px;
  line-height: 1.7;
}

.kb-doc-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kb-doc {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 9px;
  background: #fff;
  font-size: 12.5px;
}

.kb-doc-city {
  flex: 0 0 auto;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary-strong);
  font-size: 11.5px;
}

.kb-doc-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.kb-doc-chars {
  flex: 0 0 auto;
  color: var(--text-faint);
  font-size: 11.5px;
}

.profile-edit {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.avatar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.upload-btn {
  position: relative;
  overflow: hidden;
  cursor: pointer;
}

.file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.avatar-options {
  flex: 1;
  min-width: 240px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.option-block {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.option-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.presets {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.preset {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.preset:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(17, 24, 39, 0.18);
}

.preset-clear {
  display: grid;
  place-items: center;
  background: #f1f3f6;
  color: var(--text-muted);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.col-span {
  grid-column: span 2;
}

.hint-strip {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 13px;
  border-radius: 10px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 12.5px;
}

.hint-strip.is-ok {
  background: var(--success-soft);
  color: var(--success);
}

.test-result {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 10px 13px;
  border-radius: 10px;
  font-size: 12.5px;
  line-height: 1.6;
  word-break: break-word;
}

.test-result.is-ok {
  background: var(--success-soft);
  color: var(--success);
}

.test-result.is-error {
  background: var(--danger-soft);
  color: var(--danger);
}

.upload-btn.is-busy {
  pointer-events: none;
}

.model-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.model-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.model-row:hover {
  border-color: #c8d6f5;
}

.model-row.is-active {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.model-row-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.model-row-name {
  font-size: 13.5px;
  font-weight: 600;
}

.model-row-desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-row-provider {
  padding: 2px 9px;
  border-radius: 999px;
  background: #f3f4f6;
  color: var(--text-muted);
  font-size: 11.5px;
}

.model-radio {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  color: var(--primary);
}

.key-block {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 14px;
  border-radius: 12px;
  background: var(--panel-soft);
  border: 1px dashed var(--border);
}

.key-field {
  flex: 1;
  min-width: 0;
}

.cmt-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cmt-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--panel-soft);
  transition: border-color 0.16s ease, background 0.16s ease;
}

.cmt-item:hover {
  border-color: #d8dee8;
  background: #fff;
}

.cmt-cover {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  flex-shrink: 0;
  border-radius: 10px;
  overflow: hidden;
  background: #eef1f5;
  color: var(--text-faint);
  cursor: pointer;
}

.cmt-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-fallback {
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.cmt-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
}

.cmt-content {
  font-size: 13.5px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.cmt-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-faint);
}

.cmt-post {
  max-width: 240px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cmt-dot {
  color: var(--text-faint);
}

.pref-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pref-row {
  display: grid;
  grid-template-columns: 200px 1fr 38px;
  gap: 10px;
  align-items: center;
}

.pref-empty {
  padding: 14px;
  border-radius: 10px;
  background: var(--panel-soft);
  border: 1px dashed var(--border);
  text-align: center;
  font-size: 13px;
}

.coll-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.coll-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--panel-soft);
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.coll-item:hover {
  border-color: #d8dee8;
  background: #fff;
}

.coll-cover {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  flex-shrink: 0;
  border-radius: 10px;
  overflow: hidden;
  background: #eef1f5;
  color: var(--text-faint);
}

.coll-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.coll-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.coll-title {
  font-size: 13.5px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coll-meta {
  font-size: 12px;
  color: var(--text-muted);
}

.usage-skeleton {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.usage-top {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.usage-used {
  font-size: 22px;
  font-weight: 700;
  color: var(--primary-strong);
}

.usage-ratio {
  margin-left: auto;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
}

.usage-track {
  height: 9px;
  border-radius: 999px;
  background: #eef1f5;
  overflow: hidden;
}

.usage-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--grad-primary);
  transition: width 0.4s ease;
}

.usage-fill.is-warn {
  background: linear-gradient(135deg, #fbbf24, #f59e0b);
}

.usage-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12.5px;
  color: var(--text-muted);
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--panel-soft);
  transition: border-color 0.16s ease, background 0.16s ease;
}

.session-item:hover {
  border-color: #d8dee8;
  background: #fff;
}

.session-main {
  min-width: 0;
}

.session-summary {
  font-size: 13.5px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-faint);
}

.session-id {
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
}

.meta-sep {
  color: var(--text-faint);
}

@media (max-width: 620px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .col-span {
    grid-column: auto;
  }

  .pref-row {
    grid-template-columns: 1fr 1fr 38px;
  }

  .session-item {
    flex-direction: column;
    align-items: stretch;
  }

  .key-block {
    flex-direction: column;
    align-items: stretch;
  }

  .cmt-post {
    max-width: 150px;
  }
}
</style>
