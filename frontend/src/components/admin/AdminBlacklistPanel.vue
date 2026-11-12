<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/http'
import type { AdminUserItem } from '@/types'

/**
 * 黑名单：拉黑用户后，该用户不能发布动态、点赞、评论、收藏、关注等社区互动。
 * 左侧为用户检索（可拉黑），右侧为已拉黑名单（可解封）。
 */
const users = ref<AdminUserItem[]>([])
const banned = ref<AdminUserItem[]>([])
const keyword = ref('')
const loading = ref(true)
const busyId = ref<number | null>(null)
const error = ref('')
const flash = ref('')
const reasonDraft = ref<Record<number, string>>({})

const adminCount = computed(() => users.value.filter((u) => u.role === 'admin').length)

function notify(text: string) {
  flash.value = text
  window.setTimeout(() => {
    flash.value = ''
  }, 2600)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [u, b] = await Promise.all([
      adminApi.users({ keyword: keyword.value.trim(), limit: 50 }),
      adminApi.blacklist(),
    ])
    users.value = u
    banned.value = b
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载黑名单失败'
  } finally {
    loading.value = false
  }
}

async function addBan(user: AdminUserItem) {
  if (user.role === 'admin') return
  const reason = (reasonDraft.value[user.id] || '').trim()
  busyId.value = user.id
  error.value = ''
  try {
    await adminApi.addBlacklist(user.id, reason)
    notify(`已拉黑「${user.nickname}」，其发帖/点赞/评论/收藏已被禁止`)
    reasonDraft.value[user.id] = ''
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '拉黑失败'
  } finally {
    busyId.value = null
  }
}

async function removeBan(user: AdminUserItem) {
  busyId.value = user.id
  error.value = ''
  try {
    await adminApi.removeBlacklist(user.id)
    notify(`已把「${user.nickname}」移出黑名单，互动权限已恢复`)
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '解封失败'
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="blacklist">
    <div v-if="error" class="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
      <button class="btn btn-quiet btn-sm" type="button" @click="error = ''">关闭</button>
    </div>
    <Transition name="fade">
      <div v-if="flash" class="toast">{{ flash }}</div>
    </Transition>

    <section class="card block">
      <header class="block-head">
        <div>
          <h3><AppIcon name="shield" :size="15" /> 黑名单</h3>
          <p>
            被拉黑用户将无法发布动态、点赞、评论、收藏与关注；已发布内容保留，可随时解封恢复。
          </p>
        </div>
        <span class="count-badge">{{ banned.length }} 人</span>
      </header>

      <p v-if="!banned.length" class="empty">
        黑名单为空。可在下方「用户检索」中拉黑需要限制的用户。
      </p>
      <ul v-else class="user-list">
        <li v-for="user in banned" :key="user.id" class="user-row is-banned">
          <div class="user-avatar">
            <img v-if="user.avatar" :src="user.avatar" alt="" />
            <span v-else>{{ user.nickname.slice(0, 1) }}</span>
          </div>
          <div class="user-main">
            <div class="user-line">
              <span class="user-name">{{ user.nickname }}</span>
              <span class="user-account">@{{ user.username }}</span>
              <span class="tag tag-ban">已拉黑</span>
            </div>
            <span class="user-sub">
              {{ user.ban_reason ? `原因：${user.ban_reason}` : '未填写原因' }}
              <template v-if="user.banned_at"> · {{ user.banned_at }}</template>
            </span>
          </div>
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :disabled="busyId === user.id"
            @click="removeBan(user)"
          >
            <AppIcon name="check" :size="13" />
            移出黑名单
          </button>
        </li>
      </ul>
    </section>

    <section class="card block">
      <header class="block-head">
        <div>
          <h3><AppIcon name="users" :size="15" /> 用户检索 · 拉黑</h3>
          <p>按用户名或昵称搜索，填写原因后点击「拉黑」。管理员账号不可被拉黑。</p>
        </div>
        <div class="search">
          <input
            v-model="keyword"
            class="input"
            type="search"
            placeholder="搜索用户名 / 昵称"
            @keydown.enter="load"
          />
          <button class="btn btn-ghost btn-sm" type="button" @click="load">
            <AppIcon name="search" :size="14" />
            搜索
          </button>
        </div>
      </header>

      <div v-if="loading" class="user-list">
        <div v-for="i in 4" :key="i" class="skeleton" style="height: 52px" />
      </div>
      <p v-else-if="!users.length" class="empty">没有匹配的用户。</p>
      <ul v-else class="user-list">
        <li v-for="user in users" :key="user.id" class="user-row" :class="{ 'is-banned': user.banned }">
          <div class="user-avatar">
            <img v-if="user.avatar" :src="user.avatar" alt="" />
            <span v-else>{{ user.nickname.slice(0, 1) }}</span>
          </div>
          <div class="user-main">
            <div class="user-line">
              <span class="user-name">{{ user.nickname }}</span>
              <span class="user-account">@{{ user.username }}</span>
              <span v-if="user.role === 'admin'" class="tag tag-admin">管理员</span>
              <span v-if="user.banned" class="tag tag-ban">已拉黑</span>
            </div>
            <input
              v-if="!user.banned && user.role !== 'admin'"
              v-model="reasonDraft[user.id]"
              class="input reason"
              type="text"
              maxlength="60"
              placeholder="拉黑原因（可选，会通知对方）"
            />
          </div>
          <button
            v-if="user.role === 'admin'"
            class="btn btn-ghost btn-sm"
            type="button"
            disabled
            title="管理员账号不可拉黑"
          >
            不可拉黑
          </button>
          <button
            v-else-if="user.banned"
            class="btn btn-ghost btn-sm"
            type="button"
            :disabled="busyId === user.id"
            @click="removeBan(user)"
          >
            <AppIcon name="check" :size="13" />
            解封
          </button>
          <button
            v-else
            class="btn btn-danger btn-sm"
            type="button"
            :disabled="busyId === user.id"
            @click="addBan(user)"
          >
            <AppIcon name="shield" :size="13" />
            拉黑
          </button>
        </li>
      </ul>
      <p v-if="adminCount" class="foot-note">已识别 {{ adminCount }} 个管理员账号，不会被拉黑。</p>
    </section>
  </div>
</template>

<style scoped>
.blacklist {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.alert {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 13px;
}

.alert span {
  flex: 1;
}

.toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 40;
  padding: 10px 14px;
  border-radius: 10px;
  background: #111827;
  color: #fff;
  font-size: 12.5px;
  box-shadow: var(--shadow-pop);
}

.block {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
}

.block-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.block-head h3 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 15px;
  font-weight: 600;
}

.block-head p {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--text-muted);
  line-height: 1.7;
  max-width: 620px;
}

.count-badge {
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
  font-weight: 600;
}

.search {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search .input {
  width: 220px;
}

.user-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: #fff;
}

.user-row.is-banned {
  border-color: rgba(220, 38, 38, 0.28);
  background: #fff8f8;
}

.user-avatar {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 12px;
  overflow: hidden;
  background: var(--grad-primary);
  color: #fff;
  font-weight: 600;
}

.user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.user-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.user-name {
  font-size: 13.5px;
  font-weight: 600;
}

.user-account,
.user-sub {
  font-size: 11.5px;
  color: var(--text-faint);
}

.tag {
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11.5px;
}

.tag-ban {
  background: var(--danger-soft);
  color: var(--danger);
}

.tag-admin {
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.reason {
  height: 30px;
  max-width: 420px;
  font-size: 12.5px;
}

.empty,
.foot-note {
  font-size: 12.5px;
  color: var(--text-muted);
}

.skeleton {
  border-radius: 10px;
}
</style>
