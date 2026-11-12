/**
 * 消息中心共享状态：侧边栏徽标、右上角铃铛、消息页共用同一份未读数，
 * 避免三处各自轮询造成的不一致与重复请求。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { messageApi } from '@/api/messages'
import type { MessageItem } from '@/types'

export const useMessagesStore = defineStore('messages', () => {
  const unread = ref(0)
  const counts = ref<Record<string, number>>({})
  const latest = ref<MessageItem[]>([])
  const loaded = ref(false)

  let timer: number | undefined

  async function refresh(): Promise<void> {
    try {
      const res = await messageApi.summary()
      unread.value = res.unread
      counts.value = res.counts
      latest.value = res.latest
      loaded.value = true
    } catch {
      /* 未登录/网络异常时静默，不打扰用户 */
    }
  }

  function setUnread(value: number, nextCounts?: Record<string, number>): void {
    unread.value = Math.max(0, value)
    if (nextCounts) counts.value = nextCounts
  }

  /** 启动轮询（幂等，重复调用不会叠加定时器）。 */
  function startPolling(intervalMs = 20000): void {
    if (timer) return
    void refresh()
    timer = window.setInterval(() => void refresh(), intervalMs)
  }

  function stopPolling(): void {
    if (timer) {
      window.clearInterval(timer)
      timer = undefined
    }
  }

  function reset(): void {
    unread.value = 0
    counts.value = {}
    latest.value = []
    loaded.value = false
    stopPolling()
  }

  return { unread, counts, latest, loaded, refresh, setUnread, startPolling, stopPolling, reset }
})
