<script setup lang="ts">
/**
 * 右上角消息铃铛：展示真实站内消息（点赞/评论/回复/关注/收藏/提醒/用量），
 * 有未读时显示红点；点条目直达对应页面，点「查看全部」进消息中心。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import { messageApi } from '@/api/messages'
import { useMessagesStore } from '@/stores/messages'
import type { MessageItem } from '@/types'

const router = useRouter()
const store = useMessagesStore()
const open = ref(false)

const unread = computed(() => store.unread)
const items = computed(() => store.latest)

function toggle() {
  open.value = !open.value
  if (open.value) void store.refresh()
}

async function openMessage(msg: MessageItem) {
  if (!msg.read) {
    try {
      await messageApi.readOne(msg.id)
      store.setUnread(Math.max(0, store.unread - 1))
      msg.read = true
    } catch {
      /* 忽略已读失败 */
    }
  }
  open.value = false
  if (msg.post_id) {
    router.push({ name: 'post-detail', params: { id: msg.post_id } })
  } else if (msg.link && msg.link !== '/messages') {
    router.push(msg.link)
  } else {
    router.push({ name: 'messages' })
  }
}

function goAll() {
  open.value = false
  router.push({ name: 'messages' })
}

async function markAllRead() {
  try {
    const res = await messageApi.readAll()
    store.setUnread(res.unread, res.counts)
    await store.refresh()
  } catch {
    /* 忽略 */
  }
}

function onDocClick(event: MouseEvent) {
  const el = event.target as HTMLElement
  if (!el.closest('.bell-wrap')) open.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="bell-wrap">
    <button class="icon-btn" type="button" :title="`消息（${unread} 条未读）`" @click="toggle">
      <AppIcon name="bell" :size="18" />
      <span v-if="unread > 0" class="dot" />
    </button>

    <div v-if="open" class="dropdown" @click.stop>
      <div class="dd-head">
        <span>消息{{ unread ? `（${unread} 条未读）` : '' }}</span>
        <div class="dd-actions">
          <button class="link" type="button" @click="markAllRead">全部已读</button>
          <button class="link" type="button" @click="goAll">查看全部</button>
        </div>
      </div>

      <div v-if="!items.length" class="empty">
        暂无消息。和好友互动（点赞、评论、关注）后，或对智能体说「提醒我明天早上8点出发」，
        消息会汇总到这里。
      </div>

      <ul v-else class="list">
        <li
          v-for="m in items"
          :key="m.id"
          :class="{ unread: !m.read }"
          @click="openMessage(m)"
        >
          <div class="t">
            {{ m.title }}
            <span class="kind">{{ m.kind_label }}</span>
          </div>
          <div v-if="m.content" class="c">{{ m.content }}</div>
          <div class="time">{{ m.created_at }}</div>
        </li>
      </ul>

      <div class="dd-foot" @click="goAll">
        <AppIcon name="chevron-right" :size="13" />
        进入消息中心
      </div>
    </div>
  </div>
</template>

<style scoped>
.bell-wrap {
  position: relative;
}

.icon-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--bg-soft);
}

.dot {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 0 2px #fff;
}

.dropdown {
  position: absolute;
  right: 0;
  top: 42px;
  width: 320px;
  max-height: 400px;
  overflow: auto;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12);
  z-index: 40;
}

.dd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  position: sticky;
  top: 0;
  background: #fff;
}

.dd-actions {
  display: flex;
  gap: 10px;
}

.link {
  border: none;
  background: none;
  color: var(--primary, #2563eb);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.empty {
  padding: 16px 12px;
  font-size: 12px;
  color: var(--text-faint);
  line-height: 1.7;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.list li {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
}

.list li:hover {
  background: #f7f8fa;
}

.list li.unread {
  background: rgba(37, 99, 235, 0.06);
}

.t {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
}

.kind {
  padding: 1px 6px;
  border-radius: 999px;
  background: #f1f3f6;
  color: var(--text-faint);
  font-size: 10.5px;
  font-weight: 500;
}

.c {
  margin-top: 3px;
  font-size: 12px;
  color: var(--text-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.time {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-faint);
}

.dd-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px;
  color: var(--primary, #2563eb);
  font-size: 12.5px;
  cursor: pointer;
  background: #fff;
  position: sticky;
  bottom: 0;
}

.dd-foot:hover {
  background: var(--bg-soft, #f7f8fa);
}
</style>
