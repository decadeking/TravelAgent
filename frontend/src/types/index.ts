// 与后端 API 契约一一对应的类型定义

export type UserRole = 'user' | 'admin'

export interface UserInfo {
  id: number
  username: string
  nickname: string
  avatar: string
  cover?: string
  role: UserRole | string
  bio: string
  banned?: boolean
  created_at?: string
}

/** 管理后台用户项（黑名单 / 用户检索共用） */
export interface AdminUserItem {
  id: number
  username: string
  nickname: string
  avatar: string
  role: string
  banned: boolean
  ban_reason: string
  banned_at: string | null
}

export interface AuthResult {
  access_token: string
  token_type: string
  expires_in: number
  user: UserInfo
}

export interface UsageInfo {
  used_tokens: number
  quota: number
  remaining: number
  warn_ratio?: number
  warn_tokens?: number
  date: string
}

// ---- 消息中心（站内消息 / 好友） ----
export interface MessageActor {
  id: number
  nickname: string
  avatar: string
}

export interface MessageItem {
  id: number
  kind: string
  kind_label: string
  title: string
  content: string
  post_id: number | null
  link: string
  read: boolean
  created_at: string | null
  actor: MessageActor | null
}

export interface MessageListResult {
  items: MessageItem[]
  total: number
  page: number
  page_size: number
  unread: number
  counts: Record<string, number>
  kinds: Record<string, string>
}

export interface MessageSummary {
  unread: number
  counts: Record<string, number>
  latest: MessageItem[]
}

export interface FriendCard {
  id: number
  username: string
  nickname: string
  avatar: string
  bio: string
  following?: boolean
  mutual?: boolean
}

export interface UserPublic extends FriendCard {
  is_me: boolean
  followed_by: boolean
  is_friend: boolean
  followers: number
  following_count: number
}

export type TripStatus = 'draft' | 'confirmed' | 'shared'

export interface TripSummary {
  id: number
  title: string
  destination: string
  days: number
  budget: number
  status: TripStatus
  updated_at: string
  remark?: string
  start_date?: string
}

export interface TripListResult {
  items: TripSummary[]
  page: number
  page_size: number
  total: number
}

export interface ItineraryItem {
  id?: number
  seq: number
  time_slot: string
  poi_name: string
  category: string
  cost: number
  duration_min: number
  note: string
}

export interface TripDay {
  id?: number
  day_no: number
  city: string
  weather_snapshot: string
  items: ItineraryItem[]
}

export interface TripDetail {
  id: number
  user_id: number
  title: string
  destination: string
  days: number
  budget: number
  status: TripStatus
  version: number
  created_at: string
  updated_at: string
  total_cost: number
  day_list: TripDay[]
  remark?: string
  start_date?: string
}

export interface TripCreatePayload {
  title: string
  destination: string
  days: number
  budget: number
  status: TripStatus
  remark?: string
  start_date?: string
  day_list: Array<{
    day_no: number
    city: string
    weather_snapshot: string
    items: Array<Omit<ItineraryItem, 'id'>>
  }>
}

export interface TripFormResult {
  title: string
  destination: string
  days: number
  budget: number
  status: TripStatus
  remark?: string
  start_date?: string
}

export interface WeatherForecast {
  date: string
  condition: string
  high: number
  low: number
  suggestion: string
}

export interface WeatherResult {
  city: string
  forecast: WeatherForecast[]
}

export interface PoiItem {
  name: string
  category: string
  ticket: number
  duration_min: number
  rating: number
  open_time: string
  tags: string[]
  note: string
  category_label: string
}

export interface PoiResult {
  city: string
  items: PoiItem[]
}

export interface SessionSummary {
  session_id: string
  summary: string
  created_at: string | null
}

export interface SessionMessage {
  role: string
  content: string
}

export interface SessionState {
  session_id: string
  summary: string
  messages: SessionMessage[]
  slots: Record<string, unknown>
  plan_draft: PlanDraft | null
  revision_count: number
  can_resume: boolean
}

// ---- 智能体模型 ----
export interface AgentModel {
  id: string
  name: string
  provider: string
  description: string
}

export interface AgentModelsResult {
  models: AgentModel[]
  default_model: string
  provider: string
  has_api_key: boolean
}

// ---- 用户级模型配置（只需配置密钥，其余为固定配置） ----
export interface UserModelConfig {
  models: AgentModel[]
  default_model: string
  selected_model: string
  has_api_key: boolean
  has_own_api_key: boolean
}

export interface ModelConfigSaveResult {
  has_api_key: boolean
  model: string
}

// ---- 我的评论 ----
export interface MyComment {
  id: number
  content: string
  created_at: string
  post_id: number
  post_title: string
  post_city: string
  post_cover: string
}

// ---- SSE plan_update 完整草稿 ----
export interface DraftItem {
  time_slot: string
  poi_name: string
  category: string
  cost: number
  duration_min: number
  note: string
  lat?: number
  lon?: number
}

export interface DraftDay {
  day_no: number
  city: string
  weather: string
  day_cost: number
  items: DraftItem[]
}

export interface DraftBreakdown {
  ticket?: number
  hotel?: number
  meals?: number
  transport?: number
  [key: string]: number | undefined
}

export interface Citation {
  chunk_id: string
  text: string
  score: number
  city: string
  title: string
}

export interface GeoPoint {
  lat: number
  lon: number
}

export interface MapMarker extends GeoPoint {
  label: string
  meta?: string
}

export interface PlanDraft {
  title: string
  destination: string
  days: number
  budget: number
  total_cost: number
  within_budget: boolean
  over_budget: number
  ticket_total?: number
  breakdown: DraftBreakdown
  day_list: DraftDay[]
  citations: Citation[]
  warnings: string[]
  center?: GeoPoint
  degraded?: boolean
}

// ---- SSE 事件载荷 ----
export interface SseMeta {
  session_id: string
  trace_id: string
}

export interface SseToken {
  text: string
}

export interface SseToolCall {
  tool: string
  arguments: Record<string, unknown>
}

export interface SseToolResult {
  tool: string
  summary: string
  source?: 'mcp' | 'native' | string
}

export interface SseMemory {
  saved: Record<string, unknown>
}

export interface SseDone {
  session_id: string
  request_id: string
  cached: boolean
  usage?: { prompt_tokens: number; completion_tokens: number }
  revision_count?: number
  within_budget?: boolean
  trace_id?: string
  model_used?: string
  engine?: 'real' | 'offline'
  degraded?: boolean
  rag_hits?: number
  tools?: string[]
}

export interface SseError {
  code: number
  message: string
  retry_after?: number | null
  fatal?: boolean
  fallback?: boolean
}

export interface ReminderItem {
  id: number
  title: string
  detail: string
  remind_at: string | null
  status: string
  source: string
}

export interface NotificationItem {
  id: number
  title: string
  content: string
  kind: string
  read: boolean
  created_at: string | null
}

export interface NotificationList {
  unread: number
  items: NotificationItem[]
}

// ---- 媒体资源 ----
export interface MediaAsset {
  id: number
  url: string
  size: number
  mime: string
}

export interface MediaStats {
  count: number
  bytes: number
  mb: number
}

export interface MediaSyncResult {
  images_stored: number
  avatars_stored: number
  failed: number
  media_total: number
}

// ---- 知识文档上传（pdf / wps(docx) / txt / md → RAG） ----
export interface DocCleanStats {
  raw_chars: number
  clean_chars: number
  raw_lines: number
  clean_lines: number
  dropped_lines: number
  header_footer_removed: number
}

export interface DocUploadResult {
  document_id: number
  title: string
  city: string
  file_type: string
  meta: Record<string, unknown>
  clean: DocCleanStats
  chunks: number
  total_chunks: number
  vector_backend: string
  embedding_provider: string
  preview: string
}

export interface KbDocItem {
  id: number
  city: string
  title: string
  source: string
  chars: number
  created_at: string | null
}

// ---- RAG 全链路自检 ----
export interface RagSelfTestStage {
  name: string
  ok: boolean
  detail: Record<string, unknown>
}

export interface RagSelfTestResult {
  passed: boolean
  probe: string
  vector_backend: string
  embedding_provider: string
  total_chunks: number
  stages: RagSelfTestStage[]
  sample: { file: string; chars: number; preview: string }
}

// ---- 知识库概览（普通用户只读，个人设置页展示） ----
export interface KnowledgeDocBrief {
  id: number
  city: string
  title: string
  chars: number
  source: string
  created_at: string | null
}

export interface KnowledgeOverview {
  ready: boolean
  reason: string
  enabled: boolean
  vector_backend: string
  chunks: number
  documents: number
  embedding: { provider: string; model: string; dim: number }
  chunking: { size: number; overlap: number }
  retrieval: { topk: number; threshold: number; rerank: boolean }
  recent: KnowledgeDocBrief[]
}

// ---- MCP 运行状态 ----
export interface McpToolItem {
  name: string
  description: string
  input_schema?: Record<string, unknown>
}

export interface McpStatus {
  enabled: boolean
  status: string
  error: string
  transport: string
  server_module: string
  started_at: string
  tools?: string[]
  counts: {
    tools: number
    checks: number
    reloads: number
    calls: number
    failures: number
  }
}

// ---- 模型连通性测试 ----
export interface ModelTestResult {
  ok: boolean
  message: string
  model_used?: string
  status?: number
}

// ---- 世界那么大（动态社区）----
export interface PostAuthor {
  id: number
  nickname: string
  avatar: string
}

/** 帖子可见范围：public 全部可见 / friends 仅互关好友可见 / private 仅自己可见 */
export type PostVisibility = 'public' | 'friends' | 'private'

export interface PostSummary {
  id: number
  title: string
  city: string
  location: string
  images: string[]
  tags: string[]
  like_count: number
  collect_count: number
  comment_count: number
  view_count: number
  heat: number
  status: string
  visibility: PostVisibility
  created_at: string
  author: PostAuthor
  liked: boolean
  collected: boolean
  excerpt: string
}

/** 动态流条目：附带完整正文（关注好友 + 自己的动态） */
export interface MomentPost extends PostSummary {
  content: string
}

export interface FriendFeedResult {
  items: MomentPost[]
  page: number
  page_size: number
  total: number
  following_count: number
  friends_count: number
  followers_count: number
}

export interface PostComment {
  id: number
  content: string
  created_at: string
  user_id: number
  author: PostAuthor
}

export interface PostDetail extends PostSummary {
  content: string
  comments: PostComment[]
}

export interface PostListResult {
  items: PostSummary[]
  page: number
  page_size: number
  total: number
}

export interface CityChip {
  city: string
  count: number
}

export interface PostPayload {
  title: string
  content: string
  city: string
  location: string
  images: string[]
  tags: string[]
  visibility: PostVisibility
}

// ---- 管理端 ----
export interface AdminStats {
  users?: number
  posts?: number
  trips?: number
  sessions?: number
  comments?: number
  collections?: number
  kb_documents?: number
  kb_chunks?: number
  [key: string]: number | undefined
}

export interface AdminOverview {
  counters: Record<string, number>
  gauges: Record<string, number>
  p95_ms: number
  tokens_last_hour: number
  sse_connections: number
  breakers: Record<string, unknown>
}

export interface LlmSettings {
  base_url: string
  api_key?: string
  default_model: string
  temperature: number
  max_tokens: number
}

export interface RagSettings {
  enabled?: boolean
  vector_backend?: string
  vector_db_url?: string
  vector_hnsw_ef_search?: number
  embedding_provider: string
  embedding_model: string
  embedding_dim?: number
  embedding_base_url?: string
  embedding_api_key?: string
  has_embedding_key?: boolean
  chunk_size: number
  chunk_overlap: number
  topk: number
  score_threshold: number
  rerank?: boolean
}

export interface AdminSettings {
  llm: LlmSettings
  rag: RagSettings
  vector_backend?: string
  kb_documents?: number
  kb_chunks?: number
  doc_upload_ready?: boolean
  doc_upload_reason?: string
}

export interface RagSaveResult {
  kb_chunks: number
  kb_documents?: number
  vector_backend?: string
}

export interface KbDoc {
  id: number
  city: string
  title: string
  content: string
  source: string
  created_at?: string
}

export interface KbDocPayload {
  city: string
  title: string
  content: string
  source: string
}

export interface KbSearchHit {
  chunk_id: string
  text: string
  score: number
  city: string
  title: string
}

export interface FaultState {
  model_down: boolean
}
