import { request } from './http'
import type {
  AdminOverview,
  AdminSettings,
  AdminStats,
  AdminUserItem,
  FaultState,
  KbDoc,
  KbDocPayload,
  KbSearchHit,
  LlmSettings,
  McpStatus,
  McpToolItem,
  MediaStats,
  MediaSyncResult,
  PostListResult,
  PostSummary,
  RagSaveResult,
  RagSelfTestResult,
  RagSettings,
} from '@/types'

export interface AdminPostQuery {
  status?: string
  /** 可见范围筛选：public / friends / private；不传为全部 */
  visibility?: string
  page?: number
  page_size?: number
}

export const adminApi = {
  stats: () => request<AdminStats>({ url: '/admin/stats', method: 'get' }),
  overview: () => request<AdminOverview>({ url: '/admin/overview', method: 'get' }),

  posts: (params: AdminPostQuery = {}) =>
    request<PostListResult>({ url: '/admin/posts', method: 'get', params }),
  setPostStatus: (id: number | string, status: string) =>
    request<PostSummary>({ url: `/admin/posts/${id}/status`, method: 'put', params: { status } }),
  removePost: (id: number | string) =>
    request<{ deleted: number }>({ url: `/admin/posts/${id}`, method: 'delete' }),

  getSettings: () => request<AdminSettings>({ url: '/admin/settings', method: 'get' }),
  saveLlm: (payload: LlmSettings) =>
    request<AdminSettings['llm']>({ url: '/admin/settings/llm', method: 'put', data: payload }),
  saveRag: (payload: RagSettings) =>
    request<RagSaveResult>({ url: '/admin/settings/rag', method: 'put', data: payload }),

  kb: () => request<KbDoc[]>({ url: '/admin/kb', method: 'get' }),
  addKb: (payload: KbDocPayload) => request<KbDoc>({ url: '/admin/kb', method: 'post', data: payload }),
  removeKb: (id: number | string) =>
    request<{ deleted: number }>({ url: `/admin/kb/${id}`, method: 'delete' }),
  reindex: () => request<RagSaveResult>({ url: '/admin/kb/reindex', method: 'post' }),
  search: (query: string, city = '') =>
    request<{ query: string; hits: KbSearchHit[]; chunks: number }>({
      url: '/admin/kb/search',
      method: 'post',
      params: { query, city },
    }).then((res) => res.hits),

  getFault: () => request<FaultState>({ url: '/admin/fault', method: 'get' }),
  setFault: (payload: Partial<FaultState>) =>
    request<FaultState>({ url: '/admin/fault', method: 'post', data: payload }),

  mediaStats: () => request<MediaStats>({ url: '/admin/media/stats', method: 'get' }),
  syncMedia: () => request<MediaSyncResult>({ url: '/admin/media/sync', method: 'post' }),

  /** 用户检索（供选择拉黑对象）；banned=1 只看黑名单 */
  users: (params: { keyword?: string; banned?: 0 | 1; limit?: number } = {}) =>
    request<AdminUserItem[]>({ url: '/admin/users', method: 'get', params }),
  /** 黑名单列表 */
  blacklist: () => request<AdminUserItem[]>({ url: '/admin/blacklist', method: 'get' }),
  /** 拉黑用户：禁止其发帖 / 点赞 / 评论 / 收藏等 */
  addBlacklist: (userId: number | string, reason = '') =>
    request<AdminUserItem>({
      url: '/admin/blacklist', method: 'post', data: { user_id: Number(userId), reason },
    }),
  /** 移出黑名单 */
  removeBlacklist: (userId: number | string) =>
    request<AdminUserItem>({ url: `/admin/blacklist/${userId}`, method: 'delete' }),

  /** RAG 全链路自检：内置测试 txt 走完 清洗/切片/向量化/入库/检索 */
  kbSelfTest: (probe?: string) =>
    request<RagSelfTestResult>({
      url: '/admin/kb/selftest',
      method: 'post',
      params: probe ? { probe } : undefined,
    }),

  /** MCP 子进程运行状态（工具清单 / 健康检查 / 重连计数） */
  mcpStatus: () => request<McpStatus>({ url: '/mcp/status', method: 'get' }),
  mcpTools: () => request<{ status: string; error: string; tools: McpToolItem[] }>({
    url: '/mcp/tools',
    method: 'get',
  }),
}
