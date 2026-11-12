import { request } from './http'
import type { KnowledgeOverview } from '@/types'

export const knowledgeApi = {
  /** 知识库概览（普通用户只读）：开放状态、向量库、切片与检索参数、最近入库文档 */
  overview: (limit = 8) =>
    request<KnowledgeOverview>({ url: '/knowledge/overview', method: 'get', params: { limit } }),
}
