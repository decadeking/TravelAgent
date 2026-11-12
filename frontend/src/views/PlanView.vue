<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import PlanPreview from '@/components/PlanPreview.vue'
import ToolCallCard from '@/components/ToolCallCard.vue'
import { agentApi } from '@/api/agent'
import { ApiError, getToken } from '@/api/http'
import { mediaApi } from '@/api/media'
import { toolApi } from '@/api/tools'
import { tripApi } from '@/api/trips'
import { streamSseWithRetry } from '@/utils/sse'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import mascot from '@/assets/mascot.jpg'
import type {
  AgentModel,
  PlanDraft,
  SseDone,
  SseError,
  SseMemory,
  SseMeta,
  SseToolCall,
  SseToolResult,
  SseToken,
  TripCreatePayload,
} from '@/types'

interface ToolEntry {
  id: string
  tool: string
  args: Record<string, unknown>
  status: 'running' | 'done'
  summary: string
  source?: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  tools: ToolEntry[]
  streaming: boolean
  note?: string
  warning?: string
}

type ToolScope = 'all' | 'weather' | 'poi' | 'route' | 'budget'

interface ToolChip {
  key: string
  label: string
  icon: string
  tip: string
  scopes: ToolScope[]
}

interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start: () => void
  stop: () => void
}

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const auth = useAuthStore()

const messages = ref<ChatMessage[]>([])
const plan = ref<PlanDraft | null>(null)
// 行程预览折叠：默认收起；一旦有生成的行程数据自动展开；也可手动开合
const previewCollapsed = ref(true)
watch(plan, (v) => { previewCollapsed.value = !v })
const input = ref('')
const streaming = ref(false)
const errorBanner = ref('')
const toast = ref('')
const sessionId = ref<string | null>(null)
const scrollEl = ref<HTMLElement | null>(null)

const models = ref<AgentModel[]>([])
const selectedModel = ref('')
const providerName = ref('')
const hasApiKey = ref(true)
const modelOpen = ref(false)
const modelRoot = ref<HTMLElement | null>(null)
const savingTrip = ref(false)
const tripStartDate = ref('')   // 出发日期：填写后保存行程会自动开启提醒

// ---- 输入区：工具范围 / 附件 / 语音 ----
const textareaEl = ref<HTMLTextAreaElement | null>(null)
const plusRoot = ref<HTMLElement | null>(null)
const plusOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const docInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadingDoc = ref(false)

const scopeRoot = ref<HTMLElement | null>(null)
const scopeOpen = ref(false)
const toolScope = ref<ToolScope>('all')

const SCOPE_OPTIONS: Array<{ value: ToolScope; label: string }> = [
  { value: 'all', label: '完全访问' },
  { value: 'weather', label: '仅天气' },
  { value: 'poi', label: '仅景点' },
  { value: 'route', label: '仅路线' },
  { value: 'budget', label: '仅预算' },
]

const TOOL_CHIPS: ToolChip[] = [
  { key: 'weather', label: '天气', icon: 'cloud', tip: '实时天气（Open-Meteo）', scopes: ['all', 'weather'] },
  { key: 'poi', label: '景点', icon: 'compass', tip: '景点与门票推荐', scopes: ['all', 'poi'] },
  { key: 'route', label: '路线', icon: 'route', tip: '行程路线规划', scopes: ['all', 'route'] },
  { key: 'budget', label: '预算', icon: 'wallet', tip: '费用预算估算', scopes: ['all', 'budget'] },
  { key: 'geo', label: '定位', icon: 'map-pin', tip: '位置与城市定位', scopes: ['all', 'route'] },
]

// chip 的 key → 后端真实工具名（搜索类工具仅在「完全访问」时启用）
const TOOL_API_NAMES: Record<string, string[]> = {
  weather: ['get_weather'],
  poi: ['search_poi'],
  route: ['plan_route'],
  budget: ['estimate_budget'],
  geo: ['geocode'],
}

/** 依据左下角的工具范围，算出本次对话要启用的后端工具名；全部启用时返回 undefined。 */
function enabledToolNames(): string[] | undefined {
  if (toolScope.value === 'all') return undefined
  const names = TOOL_CHIPS
    .filter((chip) => chip.scopes.includes(toolScope.value))
    .flatMap((chip) => TOOL_API_NAMES[chip.key] ?? [])
  return names.length ? Array.from(new Set(names)) : undefined
}

const speechSupported =
  typeof window !== 'undefined' &&
  ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)
const ttsSupported = typeof window !== 'undefined' && 'speechSynthesis' in window
const listening = ref(false)
const speaking = ref(false)

let controller: AbortController | null = null
let toastTimer: number | undefined
let recognition: { stop: () => void } | null = null

const EXAMPLES = [
  '我要去成都玩 4 天，预算 3000 元，带小孩，不想爬山',
  '帮我规划大理 3 天行程，预算 2000 元，节奏轻松一点',
  '北京 5 天经典路线，预算 5000 元，多安排人文景点',
]

const canSend = computed(() => input.value.trim().length > 0 && !streaming.value)
const sessionLabel = computed(() => (sessionId.value ? sessionId.value : '尚未创建会话'))
const currentModel = computed(
  () => models.value.find((item) => item.id === selectedModel.value) ?? null,
)
const currentModelName = computed(() => currentModel.value?.name || selectedModel.value || '默认模型')
const currentModelBadge = computed(() => (currentModel.value?.provider || '').trim())
const scopeLabel = computed(
  () => SCOPE_OPTIONS.find((item) => item.value === toolScope.value)?.label ?? '完全访问',
)
const lastAssistantText = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const msg = messages.value[i]
    if (msg.role === 'assistant' && msg.content.trim()) return msg.content.trim()
  }
  return ''
})

function uid(): string {
  return crypto.randomUUID()
}

function scrollToBottom() {
  nextTick(() => {
    const el = scrollEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function showToast(text: string) {
  toast.value = text
  window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toast.value = ''
  }, 3200)
}

function currentAssistant(): ChatMessage | undefined {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    if (messages.value[i].role === 'assistant') return messages.value[i]
  }
  return undefined
}

function finalizeStreaming() {
  const last = currentAssistant()
  if (last) {
    last.streaming = false
    last.tools.forEach((tool) => {
      if (tool.status === 'running') tool.status = 'done'
    })
  }
  streaming.value = false
}

let lastEventId = 0   // 事件编号去重（Q28）：重连后旧事件不重复渲染

function handleEvent(event: string, data: unknown, eventId?: number) {
  if (eventId !== undefined) {
    if (eventId <= lastEventId) return   // 已处理过，跳过
    lastEventId = eventId
  }
  const assistant = currentAssistant()
  switch (event) {
    case 'meta': {
      const payload = data as SseMeta
      if (payload?.session_id) sessionId.value = payload.session_id
      break
    }
    case 'token': {
      const payload = data as SseToken
      if (assistant && typeof payload?.text === 'string') {
        assistant.content += payload.text
        scrollToBottom()
      }
      break
    }
    case 'tool_call': {
      const payload = data as SseToolCall
      if (!assistant || !payload?.tool) break
      assistant.tools.push({
        id: uid(),
        tool: payload.tool,
        args: payload.arguments ?? {},
        status: 'running',
        summary: '',
        source: 'native',   // 执行完成后由 tool_result 事件更新为 mcp
      })
      scrollToBottom()
      break
    }
    case 'tool_result': {
      const payload = data as SseToolResult
      if (!assistant || !payload?.tool) break
      const target = [...assistant.tools].reverse().find((t) => t.tool === payload.tool && t.status === 'running')
      if (target) {
        target.status = 'done'
        target.summary = payload.summary || ''
        target.source = payload.source || 'native'
      }
      break
    }
    case 'plan_update': {
      plan.value = data as PlanDraft
      break
    }
    case 'memory': {
      const payload = data as SseMemory
      const keys = payload?.saved ? Object.keys(payload.saved) : []
      if (keys.length) showToast(`已记住你的偏好：${keys.join('、')}`)
      break
    }
    case 'done': {
      const payload = data as SseDone
      if (payload?.session_id) sessionId.value = payload.session_id
      if (assistant) {
        const parts: string[] = []
        // 引擎标识：一眼区分「真实大模型」与「离线模拟」，避免误判为模板输出
        if (payload?.cached) parts.push('命中缓存')
        else if (payload?.engine === 'real') parts.push(`真实模型 ${payload.model_used || ''}`.trim())
        else parts.push('离线模拟（未配置密钥）')
        if (typeof payload?.rag_hits === 'number') parts.push(`RAG 引用 ${payload.rag_hits} 条`)
        if (payload?.tools?.length) parts.push(`工具 ${payload.tools.length} 个`)
        if (payload?.degraded) parts.push('已降级')
        if (typeof payload?.revision_count === 'number' && payload.revision_count > 0) {
          parts.push(`修订 ${payload.revision_count} 次`)
        }
        if (payload?.usage) {
          parts.push(`消耗 ${(payload.usage.prompt_tokens ?? 0) + (payload.usage.completion_tokens ?? 0)} tokens`)
        }
        assistant.note = parts.join(' · ')
      }
      finalizeStreaming()
      scrollToBottom()
      break
    }
    case 'error': {
      const payload = data as SseError
      const text = payload?.message || '规划过程出现异常'
      // 已自动降级（fallback）或非致命错误：以对话流警告条展示，不阻断页面
      if (payload?.fallback || payload?.fatal === false) {
        if (assistant) assistant.warning = text
        else errorBanner.value = text
      } else {
        errorBanner.value = text
      }
      finalizeStreaming()
      break
    }
    default:
      break
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  liveSeq += 1   // 标记新一轮对话开始：后续到达的「异步会话恢复」不得覆盖本轮实时状态

  errorBanner.value = ''
  messages.value.push({ id: uid(), role: 'user', content: text, tools: [], streaming: false })
  const assistant: ChatMessage = { id: uid(), role: 'assistant', content: '', tools: [], streaming: true }
  messages.value.push(assistant)
  input.value = ''
  streaming.value = true
  scrollToBottom()

  controller = new AbortController()
  lastEventId = 0
  const requestId = uid()   // 固定 request_id：重连时后端幂等挡住重复规划
  try {
    await streamSseWithRetry(
      (lastId) => ({
        url: '/api/agent/chat',
        body: {
          message: text,
          session_id: sessionId.value ?? undefined,
          request_id: requestId,
          model: selectedModel.value || undefined,
          tools: enabledToolNames(),
        },
        token: getToken(),
        signal: controller!.signal,
        lastEventId: lastId || undefined,
      }),
      handleEvent,
      { maxRetries: 3, onStateRestore: async () => {
        // 重连后先恢复上下文：只取最新行程草稿，不覆盖正在流式渲染的消息
        if (!sessionId.value) return
        try {
          const state = await agentApi.session(sessionId.value)
          if (state?.plan_draft) plan.value = state.plan_draft
        } catch { /* 恢复失败继续重试 */ }
      } },
    )
  } catch (err) {
    errorBanner.value = (err as Error)?.message || '连接规划服务失败'
  } finally {
    finalizeStreaming()
    controller = null
    if (!assistant.content && !assistant.tools.length) {
      assistant.content = '（未获得有效回复，请重试或稍后再试）'
    }
    saveSnapshot()   // 每轮结束刷新本地快照：切页/刷新后可完整复原本轮对话与行程
    scrollToBottom()
  }
}

function sendExample(text: string) {
  input.value = text
  send()
}

/**
 * 会话持久化：切页/刷新后不丢失上下文与「思考中的」行程草稿。
 * 只有用户主动点「新建会话」（resetSession）才会清除。
 * 按登录用户隔离存储键：防止换账号后带着上一个账号的 session_id 续聊造成串会话（403）。
 */
const LEGACY_SESSION_KEY = 'ta_active_session'
const LEGACY_SNAPSHOT_KEY = 'ta_active_snapshot'
const sessionKey = () => `ta_active_session:${auth.user?.id ?? 'anon'}`
const snapshotKey = () => `ta_active_snapshot:${auth.user?.id ?? 'anon'}`
let liveSeq = 0   // 实时对话活动序号：防止「异步会话恢复」覆盖正在进行的对话与流式渲染

function saveActiveSession() {
  try {
    if (sessionId.value) localStorage.setItem(sessionKey(), sessionId.value)
    else localStorage.removeItem(sessionKey())
  } catch {
    /* 隐私模式等场景下忽略 */
  }
}

function loadActiveSession(): string {
  try {
    return localStorage.getItem(sessionKey()) || ''
  } catch {
    return ''
  }
}

/** 存一份轻量快照（消息 + 草稿），回到页面即可先渲染，再与服务端对齐。 */
function saveSnapshot() {
  try {
    localStorage.setItem(snapshotKey(), JSON.stringify({
      session_id: sessionId.value,
      messages: messages.value.slice(-20),
      plan: plan.value,
    }))
  } catch {
    /* 快照过大或不可用时忽略 */
  }
}

function loadSnapshot(): { session_id: string; messages: ChatMessage[]; plan: PlanDraft | null } | null {
  try {
    const raw = localStorage.getItem(snapshotKey())
    if (!raw) return null
    const data = JSON.parse(raw)
    if (!data || !data.session_id) return null
    return data
  } catch {
    return null
  }
}

function clearPersistence() {
  try {
    localStorage.removeItem(sessionKey())
    localStorage.removeItem(snapshotKey())
  } catch {
    /* 忽略 */
  }
}

function resetSession() {
  if (streaming.value) {
    controller?.abort()
  }
  messages.value = []
  plan.value = null
  sessionId.value = null
  errorBanner.value = ''
  input.value = ''
  toast.value = ''
  clearPersistence()          // 只有主动删除才清除本地会话
  if (route.query.session) {
    router.replace({ name: 'plan' })
  }
}

async function restoreSession(id: string) {
  const seq = liveSeq
  try {
    const state = await agentApi.session(id)
    if (!state) {
      // 服务端已无此会话（过期或不属于当前账号）：清掉本地指针，避免反复带着旧 id 续聊
      clearPersistence()
      return
    }
    // 恢复期间用户已发起新一轮对话 / 正在流式生成 → 此时服务端快照是旧的，
    // 直接覆盖会把刚发出的提问与正在渲染的回复冲掉（表现为「问了没反应」）。
    if (seq !== liveSeq || streaming.value) return
    sessionId.value = state.session_id
    messages.value = (state.messages || []).map((m) => ({
      id: uid(),
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.content,
      tools: [],
      streaming: false,
    }))
    plan.value = state.plan_draft ?? null
    saveActiveSession()
    saveSnapshot()
    scrollToBottom()
  } catch (err) {
    errorBanner.value = (err as Error)?.message || '恢复会话失败'
  }
}

function planToTrip(draft: PlanDraft): TripCreatePayload {
  return {
    title: draft.title || `${draft.destination}行程`,
    destination: draft.destination,
    days: draft.days,
    budget: draft.budget,
    status: 'draft',
    start_date: tripStartDate.value || undefined,
    day_list: draft.day_list.map((day) => ({
      day_no: day.day_no,
      city: day.city,
      weather_snapshot: day.weather,
      items: day.items.map((item, index) => ({
        seq: index + 1,
        time_slot: item.time_slot,
        poi_name: item.poi_name,
        category: item.category,
        cost: item.cost,
        duration_min: item.duration_min,
        note: item.note,
      })),
    })),
  }
}

async function saveAsTrip() {
  if (!plan.value || savingTrip.value) return
  savingTrip.value = true
  errorBanner.value = ''
  try {
    await tripApi.create(planToTrip(plan.value))
    showToast(tripStartDate.value
      ? '已保存为行程，并开启出发提醒，正在前往「个人行程」'
      : '已保存为行程，正在前往「个人行程」')
    window.setTimeout(() => router.push({ name: 'trips' }), 600)
  } catch (err) {
    errorBanner.value = (err as Error)?.message || '保存行程失败'
  } finally {
    savingTrip.value = false
  }
}

async function loadModels() {
  try {
    const res = await agentApi.models()
    models.value = res.models ?? []
    providerName.value = res.provider || ''
    hasApiKey.value = res.has_api_key
    const preferred = ui.preferredModel
    if (preferred && res.models.some((item) => item.id === preferred)) {
      selectedModel.value = preferred
    } else {
      selectedModel.value = res.default_model || res.models[0]?.id || ''
    }
  } catch {
    /* 模型列表加载失败时使用后端默认模型 */
  }
}

function pickModel(id: string) {
  selectedModel.value = id
  ui.setPreferredModel(id)
  modelOpen.value = false
}

function pickScope(value: ToolScope) {
  toolScope.value = value
  scopeOpen.value = false
}

function chipActive(scopes: ToolScope[]): boolean {
  return scopes.includes(toolScope.value)
}

function autoResize() {
  const el = textareaEl.value
  if (!el) return
  el.style.height = 'auto'
  const max = 168
  el.style.height = `${Math.min(el.scrollHeight, max)}px`
}

function appendToInput(text: string) {
  const value = input.value
  const sep = value && !/[\s\n]$/.test(value) ? '\n' : ''
  input.value = `${value}${sep}${text}`
  nextTick(autoResize)
}

function triggerPlusUpload() {
  plusOpen.value = false
  fileInput.value?.click()
}

function triggerDocUpload() {
  plusOpen.value = false
  docInput.value?.click()
}

/** 上传位置信息：浏览器定位 → 逆地理编码（地图地点 API）→ 拼接进输入框给智能体分析 */
function plusLocation() {
  plusOpen.value = false
  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    showToast('当前浏览器不支持定位')
    return
  }
  showToast('正在获取当前位置…')
  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      const { latitude, longitude } = pos.coords
      try {
        const res = await toolApi.reverseGeocode(latitude, longitude)
        const label = res.display_name || res.name || `${latitude}, ${longitude}`
        appendToInput(`【位置信息】${label}（经纬度 ${latitude.toFixed(4)}, ${longitude.toFixed(4)}）`)
        showToast('位置已插入到输入框')
      } catch (err) {
        appendToInput(`【位置信息】经纬度 ${latitude.toFixed(4)}, ${longitude.toFixed(4)}`)
        showToast(err instanceof ApiError ? err.message : '位置已插入（仅经纬度）')
      }
    },
    () => showToast('未获取到定位权限，可在浏览器设置中允许定位'),
    { enableHighAccuracy: true, timeout: 8000 },
  )
}

async function onComposerFile(event: Event) {
  const el = event.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  uploading.value = true
  try {
    const res = await mediaApi.upload(file, 'image')
    appendToInput(`【图片】${res.url}`)
    showToast('图片已上传，已插入到输入框')
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : '图片上传失败')
  } finally {
    uploading.value = false
  }
}

/** 上传知识文档：pdf / wps(docx) / txt / md → 解析清洗 → 入 RAG 知识库 */
async function onComposerDoc(event: Event) {
  const el = event.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  uploadingDoc.value = true
  errorBanner.value = ''
  try {
    const res = await mediaApi.uploadDoc(file)
    showToast(
      `已入库：${res.title}（清洗 ${res.clean.clean_chars} 字 · 切片 ${res.chunks} 块 · `
      + `总量 ${res.total_chunks} 块 · ${res.vector_backend}）`,
    )
  } catch (err) {
    // 向量模型未配置等前置条件不满足时，后端返回「该功能暂未开放」等可读提示
    errorBanner.value = err instanceof ApiError ? err.message : '文档上传失败'
  } finally {
    uploadingDoc.value = false
  }
}

function toggleVoice() {
  if (!speechSupported) return
  if (listening.value) {
    recognition?.stop()
    return
  }
  const win = window as unknown as Record<string, unknown>
  const Ctor = (win.webkitSpeechRecognition ?? win.SpeechRecognition) as
    | (new () => SpeechRecognitionLike)
    | undefined
  if (!Ctor) return
  const inst = new Ctor()
  inst.lang = 'zh-CN'
  inst.interimResults = false
  inst.continuous = false
  inst.onresult = (event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => {
    const text = Array.from(event.results, (r) => r[0]?.transcript ?? '').join('')
    if (text) appendToInput(text)
  }
  inst.onend = () => {
    listening.value = false
  }
  inst.onerror = () => {
    listening.value = false
  }
  recognition = inst
  listening.value = true
  inst.start()
}

function toggleSpeak() {
  if (!ttsSupported || !lastAssistantText.value) return
  if (speaking.value) {
    window.speechSynthesis.cancel()
    speaking.value = false
    return
  }
  const utter = new SpeechSynthesisUtterance(lastAssistantText.value)
  utter.lang = 'zh-CN'
  utter.onend = () => {
    speaking.value = false
  }
  utter.onerror = () => {
    speaking.value = false
  }
  speaking.value = true
  window.speechSynthesis.speak(utter)
}

function onSendClick() {
  if (streaming.value) {
    controller?.abort()
    return
  }
  send()
}

function handleOutside(event: MouseEvent) {
  const target = event.target as Node
  if (modelOpen.value && modelRoot.value && !modelRoot.value.contains(target)) {
    modelOpen.value = false
  }
  if (plusOpen.value && plusRoot.value && !plusRoot.value.contains(target)) {
    plusOpen.value = false
  }
  if (scopeOpen.value && scopeRoot.value && !scopeRoot.value.contains(target)) {
    scopeOpen.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (!streaming.value) send()
  }
}

// 会话 id 变化即落本地；同时刷新轻量快照，切页回来可秒级复原
watch(sessionId, () => {
  saveActiveSession()
  saveSnapshot()
})

watch(
  () => route.query.session,
  (id) => {
    if (typeof id === 'string' && id) restoreSession(id)
  },
)

onMounted(() => {
  loadModels()
  document.addEventListener('click', handleOutside)
  // 一次性清理旧版不分账号的全局键（曾导致换账号带旧会话续聊）
  try {
    localStorage.removeItem(LEGACY_SESSION_KEY)
    localStorage.removeItem(LEGACY_SNAPSHOT_KEY)
  } catch { /* 忽略 */ }
  const id = route.query.session
  if (typeof id === 'string' && id) {
    restoreSession(id)
    return
  }
  // 无路由参数时：先用本地快照即时复原，再与服务端对齐（保证「思考中的行程」不丢）
  const savedId = loadActiveSession()
  const snap = loadSnapshot()
  if (snap && snap.session_id === savedId) {
    sessionId.value = snap.session_id
    messages.value = (snap.messages || []).map((m) => ({
      id: uid(),
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.content,
      tools: (m.tools as ToolEntry[]) || [],
      streaming: false,
    }))
    plan.value = snap.plan ?? null
    scrollToBottom()
  }
  if (savedId) {
    void restoreSession(savedId)
  }
})

onBeforeUnmount(() => {
  // 关键：切页时若仍在规划中，不 abort —— 让后端把这一轮跑完并写入会话状态，
  // 用户回到本页会通过 restoreSession 恢复，避免「思考中的行程」被丢弃。
  if (!streaming.value) {
    controller?.abort()
  }
  recognition?.stop()
  if (ttsSupported) window.speechSynthesis.cancel()
  window.clearTimeout(toastTimer)
  document.removeEventListener('click', handleOutside)
})
</script>

<template>
  <div class="plan" :class="{ 'is-preview-collapsed': previewCollapsed }">
    <section class="chat-pane">
      <header class="pane-head">
        <div class="pane-head-left">
          <span class="pane-dot" />
          <div>
            <h2 class="pane-title">规划对话</h2>
            <p class="pane-sub">会话 {{ sessionLabel }}</p>
          </div>
        </div>
        <div class="pane-head-right">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :title="previewCollapsed ? '展开行程实时预览' : '收起行程实时预览'"
            @click="previewCollapsed = !previewCollapsed"
          >
            <AppIcon name="layout" :size="14" />
            行程预览
          </button>
          <button class="btn btn-ghost btn-sm" type="button" @click="resetSession">
            <AppIcon name="refresh" :size="14" />
            重置会话
          </button>
        </div>
      </header>

      <div ref="scrollEl" class="chat-scroll">
        <div v-if="!messages.length" class="chat-intro">
          <div class="intro-mark">
            <img :src="mascot" alt="旅行吧智能规划助手" />
          </div>
          <h3>今天想去哪里旅行？</h3>
          <p>
            描述你的目的地、天数、预算与偏好，我会调用天气、景点与预算工具，
            为你生成可继续修订的行程方案。
          </p>
          <div class="examples">
            <button
              v-for="example in EXAMPLES"
              :key="example"
              class="example"
              type="button"
              @click="sendExample(example)"
            >
              <AppIcon name="chevron-right" :size="14" />
              <span>{{ example }}</span>
            </button>
          </div>
        </div>

        <div v-for="msg in messages" :key="msg.id" class="msg" :class="`msg-${msg.role}`">
          <div v-if="msg.role === 'assistant'" class="bubble-avatar">
            <img :src="mascot" alt="旅行助手" />
          </div>
          <div class="msg-body">
            <div v-if="msg.role === 'user'" class="bubble bubble-user">{{ msg.content }}</div>

            <template v-else>
              <div v-if="msg.tools.length" class="tool-stack">
                <ToolCallCard
                  v-for="tool in msg.tools"
                  :key="tool.id"
                  :tool="tool.tool"
                  :args="tool.args"
                  :status="tool.status"
                  :summary="tool.summary"
                  :source="tool.source"
                />
              </div>
              <div v-if="msg.warning" class="msg-warning">
                <AppIcon name="alert" :size="14" />
                <span>{{ msg.warning }}</span>
              </div>
              <div v-if="msg.content || msg.streaming" class="bubble bubble-ai">
                <span class="ai-text">{{ msg.content }}</span>
                <span v-if="msg.streaming" class="caret-blink" />
              </div>
              <div v-if="msg.note" class="msg-note">
                <AppIcon name="check" :size="12" />
                {{ msg.note }}
              </div>
            </template>
          </div>
        </div>
      </div>

      <Transition name="fade">
        <div v-if="errorBanner" class="error-banner">
          <AppIcon name="alert" :size="15" />
          <span>{{ errorBanner }}</span>
          <button class="btn btn-quiet btn-sm" type="button" @click="errorBanner = ''">关闭</button>
        </div>
      </Transition>

      <form class="composer" @submit.prevent="onSendClick">
        <div class="composer-card">
          <textarea
            ref="textareaEl"
            v-model="input"
            class="composer-textarea"
            rows="1"
            placeholder="描述你的旅行需求，例如：想去成都玩 4 天，预算 3000 元，带小孩…（Enter 发送 / Shift+Enter 换行）"
            :disabled="streaming"
            @keydown="onKeydown"
            @input="autoResize"
          />

          <div class="composer-bar">
            <div class="bar-left">
              <div ref="plusRoot" class="pop-wrap">
                <button
                  class="icon-btn"
                  type="button"
                  title="添加"
                  :disabled="uploading || uploadingDoc"
                  @click="plusOpen = !plusOpen"
                >
                  <span v-if="uploading || uploadingDoc" class="spinner spinner-dark" />
                  <AppIcon v-else name="plus" :size="16" />
                </button>
                <Transition name="fade">
                  <div v-if="plusOpen" class="pop-menu">
                    <button class="pop-item" type="button" @click="triggerPlusUpload">
                      <AppIcon name="image" :size="15" />
                      上传图片
                    </button>
                    <button class="pop-item" type="button" @click="plusLocation">
                      <AppIcon name="map-pin" :size="15" />
                      上传位置信息
                    </button>
                    <button class="pop-item" type="button" @click="triggerDocUpload">
                      <AppIcon name="file-text" :size="15" />
                      上传文档到知识库
                    </button>
                  </div>
                </Transition>
                <input ref="fileInput" type="file" accept="image/*" class="hidden-file" @change="onComposerFile" />
                <input
                  ref="docInput"
                  type="file"
                  accept=".pdf,.docx,.txt,.md"
                  class="hidden-file"
                  @change="onComposerDoc"
                />
              </div>

              <div ref="scopeRoot" class="pop-wrap">
                <button class="scope-btn" type="button" @click="scopeOpen = !scopeOpen">
                  <AppIcon name="alert" :size="14" class="scope-warn" />
                  <span>{{ scopeLabel }}</span>
                  <AppIcon name="chevron-down" :size="13" :class="['model-caret', { 'is-open': scopeOpen }]" />
                </button>
                <Transition name="fade">
                  <div v-if="scopeOpen" class="pop-menu scope-menu">
                    <button
                      v-for="opt in SCOPE_OPTIONS"
                      :key="opt.value"
                      class="pop-item"
                      type="button"
                      :class="{ 'is-active': opt.value === toolScope }"
                      @click="pickScope(opt.value)"
                    >
                      <span>{{ opt.label }}</span>
                      <AppIcon v-if="opt.value === toolScope" name="check" :size="14" class="model-check" />
                    </button>
                  </div>
                </Transition>
              </div>

              <div class="tool-chips">
                <span
                  v-for="tool in TOOL_CHIPS"
                  :key="tool.key"
                  class="tool-chip"
                  :class="{ 'is-on': chipActive(tool.scopes) }"
                  :title="tool.tip"
                >
                  <AppIcon :name="tool.icon" :size="14" />
                </span>
              </div>
            </div>

            <div class="bar-right">
              <div ref="modelRoot" class="pop-wrap">
                <button class="model-trigger" type="button" @click="modelOpen = !modelOpen">
                  <span class="model-name">{{ currentModelName }}</span>
                  <span v-if="currentModelBadge" class="model-badge">{{ currentModelBadge }}</span>
                  <AppIcon name="chevron-down" :size="13" :class="['model-caret', { 'is-open': modelOpen }]" />
                </button>
                <Transition name="fade">
                  <div v-if="modelOpen" class="model-pop">
                    <div class="model-pop-head">
                      <span>选择模型</span>
                      <span v-if="providerName" class="model-provider">{{ providerName }}</span>
                    </div>
                    <button
                      v-for="model in models"
                      :key="model.id"
                      class="model-item"
                      type="button"
                      @click="pickModel(model.id)"
                    >
                      <div class="model-item-main">
                        <span class="model-item-name">{{ model.name }}</span>
                        <span class="model-item-desc">{{ model.description || model.provider }}</span>
                      </div>
                      <AppIcon v-if="model.id === selectedModel" name="check" :size="15" class="model-check" />
                    </button>
                    <div v-if="!models.length" class="model-empty">暂无可选模型</div>
                    <div v-if="!hasApiKey" class="model-notice">
                      <AppIcon name="info" :size="13" />
                      未配置密钥，将使用离线模拟
                    </div>
                  </div>
                </Transition>
              </div>

              <button
                class="icon-btn"
                type="button"
                :class="{ 'is-active': listening }"
                :disabled="!speechSupported || streaming"
                :title="speechSupported ? (listening ? '停止录音' : '语音输入') : '当前浏览器不支持语音输入'"
                @click="toggleVoice"
              >
                <AppIcon name="mic" :size="16" />
              </button>

              <button
                class="icon-btn"
                type="button"
                :class="{ 'is-active': speaking }"
                :disabled="!ttsSupported || !lastAssistantText"
                :title="ttsSupported ? (speaking ? '停止播报' : '朗读最后一条回复') : '当前浏览器不支持语音播报'"
                @click="toggleSpeak"
              >
                <AppIcon name="audio-wave" :size="16" />
              </button>

              <button
                class="send-btn"
                type="submit"
                :class="{ 'is-stop': streaming }"
                :disabled="!canSend && !streaming"
                :title="streaming ? '停止生成' : '发送'"
              >
                <AppIcon v-if="streaming" name="stop" :size="13" fill="currentColor" />
                <AppIcon v-else name="arrow-up" :size="17" />
              </button>
            </div>
          </div>
        </div>

        <div class="composer-hint">
          <AppIcon name="info" :size="13" />
          <span class="hint-dot">·</span>
          <template v-if="!hasApiKey">未配置密钥，将使用离线模拟；可在个人设置中填入 API Key</template>
          <template v-else-if="sessionId">可继续对话修订，如「第二天换个便宜点的」</template>
          <template v-else>首轮对话将创建新的规划会话</template>
          <span class="hint-sep">AI 生成内容仅供参考，请结合实际情况核对。</span>
        </div>
      </form>
    </section>

    <aside v-show="!previewCollapsed" class="preview-pane">
      <header class="pane-head">
        <div class="pane-head-left">
          <AppIcon name="calendar" :size="16" />
          <div>
            <h2 class="pane-title">行程实时预览</h2>
            <p class="pane-sub">{{ plan ? '已根据最新对话更新' : '等待生成…' }}</p>
          </div>
        </div>
        <div class="pane-head-right">
          <span v-if="streaming" class="live">
            <span class="live-dot" />
            生成中
          </span>
          <label class="head-date" title="填写出发日期后，保存行程会自动开启提醒">
            <AppIcon name="calendar" :size="14" />
            <input v-model="tripStartDate" type="date" class="head-date-input" />
          </label>
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :disabled="!plan || savingTrip"
            @click="saveAsTrip"
          >
            <span v-if="savingTrip" class="spinner spinner-dark" />
            <AppIcon v-else name="bookmark" :size="14" />
            保存为行程
          </button>
          <button class="icon-btn btn-sm" type="button" title="收起预览" @click="previewCollapsed = true">
            <AppIcon name="chevron-right" :size="15" />
          </button>
        </div>
      </header>
      <div class="preview-scroll">
        <PlanPreview :plan="plan" :loading="streaming" />
      </div>
    </aside>

    <Transition name="fade">
      <div v-if="toast" class="toast">
        <AppIcon name="bookmark" :size="14" />
        {{ toast }}
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.plan {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr);
  height: calc(100vh - 64px);
  background: var(--bg);
}

/* 折叠态：行程预览隐藏，对话区占满整行 */
.plan.is-preview-collapsed {
  grid-template-columns: minmax(0, 1fr);
}

.plan.is-preview-collapsed .chat-pane {
  border-right: none;
}

.chat-pane,
.preview-pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.chat-pane {
  border-right: 1px solid var(--border);
  background: #fff;
}

.preview-pane {
  background: var(--bg);
}

.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  height: 58px;
  padding: 0 18px;
  border-bottom: 1px solid var(--border);
  background: #fff;
}

.pane-head-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: var(--text-muted);
}

.pane-head-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.pane-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.pane-sub {
  font-size: 11.5px;
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pane-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.15);
}

.live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary-strong);
  font-size: 12px;
  font-weight: 500;
}

.head-date {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--text-muted);
}

.head-date-input {
  width: 120px;
  border: none;
  background: transparent;
  font-size: 12px;
  color: var(--text);
}

.head-date-input:focus {
  outline: none;
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.1s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1.15);
  }
}

.chat-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 22px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-intro {
  margin: auto;
  max-width: 460px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

/* 规划页中心形象：圆形助手头像，渐变描边贴合网站蓝紫主色 */
.intro-mark {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  overflow: hidden;
  background: #fff;
  border: 2px solid transparent;
  background:
    linear-gradient(#fff, #fff) padding-box,
    var(--grad-primary) border-box;
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.28);
}

.intro-mark img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.chat-intro h3 {
  font-size: 17px;
  font-weight: 650;
}

.chat-intro p {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.8;
}

.examples {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  margin-top: 10px;
}

.example {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  color: var(--text-muted);
  font-size: 13px;
  text-align: left;
  transition: border-color 0.16s ease, background 0.16s ease, color 0.16s ease, transform 0.16s ease;
}

.example:hover {
  border-color: #c8d6f5;
  background: var(--primary-soft);
  color: var(--primary-strong);
  transform: translateX(2px);
}

.msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.msg-user {
  justify-content: flex-end;
}

.msg-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 86%;
  min-width: 0;
}

.msg-user .msg-body {
  align-items: flex-end;
}

/* 助手气泡左侧头像：与页中心形象同步，改为圆形人物头像 */
.bubble-avatar {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 50%;
  overflow: hidden;
  border: 1.5px solid transparent;
  background:
    linear-gradient(#fff, #fff) padding-box,
    var(--grad-primary) border-box;
  box-shadow: 0 1px 4px rgba(59, 130, 246, 0.3);
}

.bubble-avatar img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.bubble {
  padding: 11px 14px;
  border-radius: 14px;
  font-size: 13.5px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble-user {
  background: var(--grad-primary);
  color: #fff;
  border-bottom-right-radius: 5px;
}

.bubble-ai {
  background: #fff;
  border: 1px solid var(--border);
  border-bottom-left-radius: 5px;
  box-shadow: var(--shadow-card);
}

.ai-text {
  white-space: pre-wrap;
}

.caret-blink {
  display: inline-block;
  width: 7px;
  height: 15px;
  margin-left: 2px;
  vertical-align: -2px;
  border-radius: 2px;
  background: var(--primary);
  animation: blink 1s steps(2, start) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.tool-stack {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.msg-note {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--text-faint);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 16px 8px;
  padding: 9px 12px;
  border-radius: 10px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.error-banner span {
  flex: 1;
}

.msg-warning {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--warning-soft);
  border: 1px solid #fbdba7;
  color: var(--warning);
  font-size: 12.5px;
  line-height: 1.6;
}

.composer {
  padding: 12px 16px 14px;
  border-top: 1px solid var(--border);
  background: #fff;
}

.composer-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 14px 10px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: #fff;
  box-shadow: var(--shadow-card);
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.composer-card:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
}

.composer-textarea {
  width: 100%;
  min-height: 26px;
  max-height: 168px;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 14px;
  line-height: 1.7;
  resize: none;
  overflow-y: auto;
}

.composer-textarea:focus {
  outline: none;
}

.composer-textarea:disabled {
  color: var(--text-faint);
}

.composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.bar-left,
.bar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.bar-left {
  flex: 1;
  min-width: 0;
}

.bar-right {
  flex-shrink: 0;
}

.pop-wrap {
  position: relative;
  display: inline-flex;
}

.hidden-file {
  display: none;
}

.icon-btn {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--text-muted);
  transition: background 0.14s ease, color 0.14s ease;
}

.icon-btn:hover:not(:disabled) {
  background: #f1f3f6;
  color: var(--text);
}

.icon-btn.is-active {
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.icon-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.scope-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  color: var(--text-muted);
  font-size: 12.5px;
  font-weight: 500;
  transition: border-color 0.14s ease, background 0.14s ease, color 0.14s ease;
}

.scope-btn:hover {
  border-color: #f0d3a6;
  background: var(--warning-soft);
  color: var(--warning);
}

.scope-warn {
  color: var(--warning);
}

.tool-chips {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  overflow: hidden;
}

.tool-chip {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 8px;
  background: #f3f4f6;
  color: var(--text-faint);
  transition: background 0.14s ease, color 0.14s ease;
}

.tool-chip.is-on {
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.model-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  max-width: 210px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: var(--text);
  font-size: 12.5px;
  font-weight: 500;
  transition: background 0.14s ease;
}

.model-trigger:hover {
  background: #f1f3f6;
}

.model-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-badge {
  padding: 1px 6px;
  border-radius: 6px;
  background: #f1f3f6;
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 500;
}

.model-caret {
  color: var(--text-faint);
  transition: transform 0.18s ease;
}

.model-caret.is-open {
  transform: rotate(180deg);
}

.pop-menu {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  min-width: 168px;
  padding: 5px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-pop);
  z-index: 60;
}

.scope-menu {
  min-width: 142px;
}

.scope-menu .pop-item {
  justify-content: space-between;
}

.pop-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  text-align: left;
  transition: background 0.14s ease;
}

.pop-item:hover {
  background: #f5f6f8;
}

.pop-item.is-active {
  color: var(--primary-strong);
  font-weight: 600;
}

.send-btn {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border: none;
  border-radius: 50%;
  background: #22c55e;
  color: #fff;
  transition: background 0.15s ease;
}

.send-btn:hover:not(:disabled) {
  background: #16a34a;
}

.send-btn:disabled {
  background: #d6dbe1;
  cursor: not-allowed;
}

.send-btn.is-stop {
  background: #1f2937;
}

.send-btn.is-stop:hover:not(:disabled) {
  background: #111827;
}

.model-pop {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  width: 288px;
  padding: 6px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-pop);
  z-index: 60;
}

.model-pop-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 10px;
  font-size: 11.5px;
  color: var(--text-faint);
}

.model-provider {
  padding: 1px 7px;
  border-radius: 999px;
  background: #f3f4f6;
}

.model-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: 9px;
  background: transparent;
  text-align: left;
  transition: background 0.14s ease;
}

.model-item:hover {
  background: #f5f6f8;
}

.model-item-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.model-item-name {
  font-size: 13px;
  font-weight: 500;
}

.model-item-desc {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-check {
  color: var(--primary);
}

.model-empty {
  padding: 14px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-faint);
}

.model-notice {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  padding: 7px 10px;
  border-radius: 8px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 11.5px;
}

.composer-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 11.5px;
  color: var(--text-faint);
}

.preview-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
}

.toast {
  position: absolute;
  right: 22px;
  bottom: 22px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 10px 14px;
  border-radius: 10px;
  background: #111827;
  color: #fff;
  font-size: 12.5px;
  box-shadow: var(--shadow-pop);
  z-index: 40;
}

@media (max-width: 900px) {
  .plan {
    grid-template-columns: 1fr;
    height: auto;
  }

  .chat-pane {
    border-right: none;
    border-bottom: 1px solid var(--border);
    height: calc(100vh - 118px);
  }

  .preview-pane {
    height: auto;
  }

  .preview-scroll {
    overflow: visible;
  }

  .msg-body {
    max-width: 92%;
  }
}

@media (max-width: 600px) {
  .tool-chips {
    display: none;
  }

  .model-trigger {
    max-width: 132px;
  }

  .model-pop {
    width: min(288px, 76vw);
  }
}
</style>
