import { request } from './http'
import type { MessageListResult, MessageSummary } from '@/types'

export interface MessageQuery {
  kind?: string
  unread_only?: boolean
  page?: number
  page_size?: number
}

export const messageApi = {
  list: (params: MessageQuery = {}) =>
    request<MessageListResult>({ url: '/messages', method: 'get', params }),
  // 轻量接口：侧边栏徽标 / 右上角铃铛轮询用
  summary: () => request<MessageSummary>({ url: '/messages/summary', method: 'get' }),
  readAll: (kind?: string) =>
    request<{ unread: number; counts: Record<string, number> }>({
      url: '/messages/read',
      method: 'post',
      params: kind ? { kind } : {},
    }),
  readOne: (id: number) =>
    request<{ id: number; unread: number }>({ url: `/messages/${id}/read`, method: 'post' }),
  remove: (id: number) =>
    request<{ deleted: number; unread: number }>({ url: `/messages/${id}`, method: 'delete' }),
  clear: () =>
    request<{ cleared: boolean; unread: number }>({ url: '/messages', method: 'delete' }),
}
