import { request } from './http'
import type {
  AgentModelsResult,
  NotificationList,
  ReminderItem,
  SessionState,
  SessionSummary,
} from '@/types'

export const agentApi = {
  sessions: () => request<SessionSummary[]>({ url: '/agent/sessions', method: 'get' }),
  session: (sessionId: string) =>
    request<SessionState | null>({ url: `/agent/sessions/${sessionId}`, method: 'get' }),
  models: () => request<AgentModelsResult>({ url: '/agent/models', method: 'get' }),
  // 行程提醒 / 站内通知
  reminders: () => request<ReminderItem[]>({ url: '/agent/reminders', method: 'get' }),
  cancelReminder: (id: number) =>
    request<{ cancelled: number }>({ url: `/agent/reminders/${id}`, method: 'delete' }),
  notifications: () =>
    request<NotificationList>({ url: '/agent/notifications', method: 'get' }),
  readNotifications: () =>
    request<{ ok: boolean }>({ url: '/agent/notifications/read', method: 'post' }),
}
