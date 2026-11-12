<script setup lang="ts">
/**
 * 消息中心：把个人中心的「评论 / Token 用量 / 点赞 / 关注 / 收藏」统一收拢到这里。
 *  - 消息：他人点赞/评论/回复/关注、收藏成功回执、Token 用量提醒、行程提醒
 *  - 好友：关注即好友
 *  - 收藏 / 评论：原个人中心的两个板块迁移于此
 *  - 用量：Token 用量 + 提醒阈值
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { ApiError } from '@/api/http'
import { messageApi } from '@/api/messages'
import { postApi } from '@/api/posts'
import { userApi } from '@/api/users'
import { formatDateTime, formatNumber } from '@/utils/format'
import type { FriendCard, MessageItem, MyComment, PostSummary, UsageInfo } from '@/types'

const route = useRoute()
const router = useRouter()

type TabKey = 'messages' | 'friends' | 'collections' | 'comments' | 'usage'
const tab = ref<TabKey>('messages')

const TABS: Array<{ key: TabKey; label: string; icon: string }> = [
  { key: 'messages', label: '消息', icon: 'bell' },
  { key: 'friends', label: '好友', icon: 'users' },
  { key: 'collections', label: '我的收藏', icon: 'star' },
  { key: 'comments', label: '我的评论', icon: 'message' },
  { key: 'usage', label: 'Token 用量', icon: 'activity' },
]

const error = ref('')
const flash = ref('')

// ---- 消息 ----
const messages = ref<MessageItem[]>([])
const counts = ref<Record<string, number>>({})
const kinds = ref<Record<string, string>>({})
const unread = ref(0)
const kindFilter = ref('all')
const loadingMessages = ref(true)

// ---- 好友 ----
const friends = ref<FriendCard[]>([])
const followingList = ref<FriendCard[]>([])
const discover = ref<FriendCard[]>([])
const loadingFriends = ref(false)
const busyFollow = ref<Record<number, boolean>>({})

// ---- 收藏 / 评论 ----
const collections = ref<PostSummary[]>([])
const myComments = ref<MyComment[]>([])
const loadingCollections = ref(false)
const loadingComments = ref(false)
const failedCovers = ref<Record<number, boolean>>({})

// ---- 用量 ----
const usage = ref<UsageInfo | null>(null)
const loadingUsage = ref(false)
const warnRatio = ref(0.8)
const savingWarn = ref(false)

const THUMB_GRADIENTS = [
  'linear-gradient(135deg,#6366f1,#3b82f6)',
  'linear-gradient(135deg,#0ea5e9,#22d3ee)',
  'linear-gradient(135deg,#f59e0b,#f97316)',
  'linear-gradient(135deg,#10b981,#34d399)',
  'linear-gradient(135deg,#8b5cf6,#d946ef)',
  'linear-gradient(135deg,#ef4444,#f97316)',
]

function thumbStyle(seed: string) {
  let h = 0
  const key = seed || 'travel'
  for (let i = 0; i < key.length; i += 1) h = (h * 31 + key.charCodeAt(i)) % 997
  return { background: THUMB_GRADIENTS[h % THUMB_GRADIENTS.length] }
}

function markCoverFailed(id: number) {
  failedCovers.value[id] = true
}

const usageRatio = computed(() => {
  if (!usage.value || !usage.value.quota) return 0
  return Math.min(100, Math.round((usage.value.used_tokens / usage.value.quota) * 100))
})

const messageTabs = computed(() => {
  const base = [{ key: 'all', label: '全部', count: unread.value }]
  for (const [key, label] of Object.entries(kinds.value)) {
    base.push({ key, label, count: counts.value[key] ?? 0 })
  }
  return base
})

function notify(text: string) {
  flash.value = text
  window.setTimeout(() => {
    flash.value = ''
  }, 3000)
}

async function loadMessages() {
  loadingMessages.value = true
  try {
    const res = await messageApi.list({
      kind: kindFilter.value === 'all' ? undefined : kindFilter.value,
      page_size: 50,
    })
    messages.value = res.items
    counts.value = res.counts
    kinds.value = res.kinds
    unread.value = res.unread
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载消息失败'
  } finally {
    loadingMessages.value = false
  }
}

async function markAllRead() {
  try {
    const res = await messageApi.readAll(kindFilter.value === 'all' ? undefined : kindFilter.value)
    unread.value = res.unread
    counts.value = res.counts
    messages.value = messages.value.map((m) => ({ ...m, read: true }))
  } catch {
    /* 忽略 */
  }
}

async function openMessage(msg: MessageItem) {
  if (!msg.read) {
    try {
      await messageApi.readOne(msg.id)
      msg.read = true
      unread.value = Math.max(0, unread.value - 1)
      if (msg.kind) counts.value[msg.kind] = Math.max(0, (counts.value[msg.kind] ?? 1) - 1)
    } catch {
      /* 忽略 */
    }
  }
  if (msg.post_id) {
    router.push({ name: 'post-detail', params: { id: msg.post_id } })
  } else if (msg.link && msg.link !== '/messages') {
    router.push(msg.link)
  }
}

async function removeMessage(msg: MessageItem) {
  try {
    const res = await messageApi.remove(msg.id)
    messages.value = messages.value.filter((m) => m.id !== msg.id)
    unread.value = res.unread
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

async function clearAll() {
  if (!window.confirm('确认清空全部消息？此操作不可恢复。')) return
  try {
    await messageApi.clear()
    messages.value = []
    unread.value = 0
    counts.value = {}
    notify('消息已清空')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '清空失败'
  }
}

async function loadFriends() {
  loadingFriends.value = true
  try {
    const [f, fw, d] = await Promise.all([
      userApi.friends(), userApi.following(), userApi.discover(),
    ])
    friends.value = f
    followingList.value = fw
    discover.value = d
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载好友失败'
  } finally {
    loadingFriends.value = false
  }
}

async function toggleFollow(person: FriendCard) {
  busyFollow.value[person.id] = true
  try {
    const res = await userApi.toggleFollow(person.id)
    notify(res.following ? `关注成功：${person.nickname}` : `已取消关注 ${person.nickname}`)
    await loadFriends()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
  } finally {
    busyFollow.value[person.id] = false
  }
}

async function loadCollections() {
  loadingCollections.value = true
  try {
    collections.value = await postApi.collections()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载收藏失败'
  } finally {
    loadingCollections.value = false
  }
}

async function uncollect(post: PostSummary) {
  try {
    await postApi.collect(post.id)
    collections.value = collections.value.filter((item) => item.id !== post.id)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
  }
}

async function loadComments() {
  loadingComments.value = true
  try {
    myComments.value = await postApi.myComments()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载评论失败'
  } finally {
    loadingComments.value = false
  }
}

async function removeComment(comment: MyComment) {
  if (!window.confirm('确认删除这条留言？')) return
  try {
    await postApi.removeComment(comment.id)
    myComments.value = myComments.value.filter((item) => item.id !== comment.id)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

async function loadUsage() {
  loadingUsage.value = true
  try {
    usage.value = await userApi.getUsage()
    warnRatio.value = usage.value.warn_ratio ?? 0.8
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载用量失败'
  } finally {
    loadingUsage.value = false
  }
}

async function saveWarnRatio() {
  savingWarn.value = true
  try {
    await userApi.savePreferences({ token_warn_ratio: String(warnRatio.value) })
    await loadUsage()
    notify(`提醒阈值已设为 ${Math.round(warnRatio.value * 100)}%`)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存阈值失败'
  } finally {
    savingWarn.value = false
  }
}

function switchTab(key: TabKey) {
  tab.value = key
  if (key === 'messages') loadMessages()
  else if (key === 'friends') loadFriends()
  else if (key === 'collections') loadCollections()
  else if (key === 'comments') loadComments()
  else if (key === 'usage') loadUsage()
}

function openPost(id: number) {
  router.push({ name: 'post-detail', params: { id } })
}

/** 点击头像 / 昵称进入该用户主页 */
function openUser(id: number) {
  if (!id) return
  router.push({ name: 'user-profile', params: { id } })
}

onMounted(() => {
  const t = route.query.tab
  if (typeof t === 'string' && TABS.some((x) => x.key === t)) tab.value = t as TabKey
  switchTab(tab.value)
})
</script>

<template>
  <div class="messages">
    <div v-if="error" class="flash is-error">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
    </div>
    <div v-if="flash" class="flash">
      <AppIcon name="check" :size="14" />
      <span>{{ flash }}</span>
    </div>

    <!-- 板块切换 -->
    <div class="tabs card">
      <button
        v-for="item in TABS"
        :key="item.key"
        class="tab"
        type="button"
        :class="{ 'is-active': tab === item.key }"
        @click="switchTab(item.key)"
      >
        <AppIcon :name="item.icon" :size="15" />
        {{ item.label }}
        <span v-if="item.key === 'messages' && unread" class="tab-dot">{{ unread }}</span>
      </button>
    </div>

    <!-- 消息 -->
    <section v-if="tab === 'messages'" class="card section">
      <header class="section-head">
        <div>
          <h2>消息</h2>
          <span class="muted">他人点赞 / 评论 / 回复 / 关注你，以及收藏回执、用量提醒都会出现在这里</span>
        </div>
        <div class="head-actions">
          <button class="btn btn-ghost btn-sm" type="button" @click="markAllRead">全部已读</button>
          <button class="btn btn-ghost btn-sm" type="button" @click="clearAll">清空</button>
        </div>
      </header>

      <div class="chips">
        <button
          v-for="k in messageTabs"
          :key="k.key"
          class="chip"
          type="button"
          :class="{ 'is-on': kindFilter === k.key }"
          @click="kindFilter = k.key; loadMessages()"
        >
          {{ k.label }}
          <span v-if="k.count" class="chip-count">{{ k.count }}</span>
        </button>
      </div>

      <div v-if="loadingMessages" class="list">
        <div v-for="i in 4" :key="i" class="skeleton" style="height: 56px" />
      </div>

      <EmptyState
        v-else-if="!messages.length"
        title="暂无消息"
        description="和好友互动（点赞、评论、关注）后，消息会汇总到这里。"
        action-text="去世界那么大逛逛"
        @action="router.push({ name: 'feed' })"
      />

      <ul v-else class="list">
        <li
          v-for="msg in messages"
          :key="msg.id"
          class="msg-item"
          :class="{ 'is-unread': !msg.read }"
          @click="openMessage(msg)"
        >
          <UserAvatar
            v-if="msg.actor"
            :src="msg.actor.avatar"
            :name="msg.actor.nickname"
            :size="36"
            :radius="12"
            :user-id="msg.actor.id"
          />
          <span v-else class="kind-icon" :class="`kind-${msg.kind}`">
            <AppIcon :name="msg.kind === 'token' ? 'activity' : msg.kind === 'collect' ? 'star' : msg.kind === 'system' ? 'info' : 'bell'" :size="16" />
          </span>
          <div class="msg-main">
            <div class="msg-top">
              <span class="msg-title">{{ msg.title }}</span>
              <span class="msg-kind">{{ msg.kind_label }}</span>
            </div>
            <p v-if="msg.content" class="msg-content">{{ msg.content }}</p>
            <span class="msg-time">{{ msg.created_at }}</span>
          </div>
          <button class="btn btn-quiet btn-sm" type="button" title="删除" @click.stop="removeMessage(msg)">
            <AppIcon name="trash" :size="14" />
          </button>
        </li>
      </ul>
    </section>

    <!-- 好友 -->
    <section v-else-if="tab === 'friends'" class="card section">
      <header class="section-head">
        <div>
          <h2>好友</h2>
          <span class="muted">只有互相关注才会成为好友；单向关注只出现在下方「我的关注」</span>
        </div>
        <span class="count-badge">{{ friends.length }}</span>
      </header>

      <div v-if="loadingFriends" class="list">
        <div v-for="i in 3" :key="i" class="skeleton" style="height: 52px" />
      </div>

      <EmptyState
        v-else-if="!friends.length"
        title="还没有好友"
        description="关注感兴趣的旅行者后，对方也回关你，你们才会成为好友。"
      />

      <ul v-else class="list">
        <li v-for="f in friends" :key="f.id" class="friend-item">
          <UserAvatar :src="f.avatar" :name="f.nickname" :size="38" :radius="12" :user-id="f.id" />
          <div class="friend-main is-link" @click="openUser(f.id)">
            <span class="friend-name">
              {{ f.nickname }}
              <span class="mutual">互关</span>
            </span>
            <span class="friend-bio">{{ f.bio || '这位旅行者很低调～' }}</span>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="toggleFollow(f)">
            取消关注
          </button>
        </li>
      </ul>

      <header class="section-head sub-head">
        <div>
          <h3>我的关注</h3>
          <span class="muted">你关注的人；对方回关后即成为好友</span>
        </div>
        <span class="count-badge">{{ followingList.length }}</span>
      </header>
      <div v-if="!followingList.length" class="hint-line muted">
        还没有关注任何人，去下面「可能认识的人」里看看吧。
      </div>
      <ul v-else class="list">
        <li v-for="p in followingList" :key="p.id" class="friend-item">
          <UserAvatar :src="p.avatar" :name="p.nickname" :size="38" :radius="12" :user-id="p.id" />
          <div class="friend-main is-link" @click="openUser(p.id)">
            <span class="friend-name">
              {{ p.nickname }}
              <span v-if="p.mutual" class="mutual">互关</span>
              <span v-else class="pending">待回关</span>
            </span>
            <span class="friend-bio">{{ p.bio || '这位旅行者很低调～' }}</span>
          </div>
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :disabled="busyFollow[p.id]"
            @click="toggleFollow(p)"
          >
            <span v-if="busyFollow[p.id]" class="spinner spinner-dark" />
            取消关注
          </button>
        </li>
      </ul>

      <header class="section-head sub-head">
        <div>
          <h3>可能认识的人</h3>
        </div>
      </header>
      <div v-if="!discover.length" class="hint-line muted">暂时没有可推荐的用户。</div>
      <ul v-else class="list">
        <li v-for="p in discover" :key="p.id" class="friend-item">
          <UserAvatar :src="p.avatar" :name="p.nickname" :size="38" :radius="12" :user-id="p.id" />
          <div class="friend-main is-link" @click="openUser(p.id)">
            <span class="friend-name">{{ p.nickname }}</span>
            <span class="friend-bio">{{ p.bio || '这位旅行者很低调～' }}</span>
          </div>
          <button
            class="btn btn-primary btn-sm"
            type="button"
            :disabled="busyFollow[p.id]"
            @click="toggleFollow(p)"
          >
            <span v-if="busyFollow[p.id]" class="spinner" />
            关注
          </button>
        </li>
      </ul>
    </section>

    <!-- 我的收藏 -->
    <section v-else-if="tab === 'collections'" class="card section">
      <header class="section-head">
        <div>
          <h2>我的收藏</h2>
          <span class="muted">在世界那么大收藏过的动态</span>
        </div>
        <span class="count-badge">{{ collections.length }}</span>
      </header>

      <div v-if="loadingCollections" class="list">
        <div v-for="i in 2" :key="i" class="skeleton" style="height: 56px" />
      </div>

      <EmptyState
        v-else-if="!collections.length"
        title="还没有收藏"
        description="在世界那么大遇到喜欢的动态，点一下星标就会出现在这里。"
        action-text="去逛逛"
        @action="router.push({ name: 'feed' })"
      />

      <ul v-else class="list">
        <li v-for="post in collections" :key="post.id" class="coll-item" @click="openPost(post.id)">
          <div class="cover" :style="failedCovers[post.id] ? thumbStyle(post.city || post.title) : undefined">
            <img
              v-if="post.images?.[0] && !failedCovers[post.id]"
              :src="post.images[0]"
              :alt="post.title"
              loading="lazy"
              @error="markCoverFailed(post.id)"
            />
            <span v-else class="cover-fallback">{{ (post.city || '旅行').slice(0, 2) }}</span>
          </div>
          <div class="coll-main">
            <span class="coll-title">{{ post.title }}</span>
            <span class="coll-meta">{{ post.city }} · 收藏 {{ post.collect_count }}</span>
          </div>
          <button class="btn btn-quiet btn-sm" type="button" @click.stop="uncollect(post)">
            <AppIcon name="star" :size="14" fill="currentColor" />
            取消收藏
          </button>
        </li>
      </ul>
    </section>

    <!-- 我的评论 -->
    <section v-else-if="tab === 'comments'" class="card section">
      <header class="section-head">
        <div>
          <h2>我的评论</h2>
          <span class="muted">你在世界那么大发表过的留言</span>
        </div>
        <span class="count-badge">{{ myComments.length }}</span>
      </header>

      <div v-if="loadingComments" class="list">
        <div v-for="i in 2" :key="i" class="skeleton" style="height: 56px" />
      </div>

      <EmptyState
        v-else-if="!myComments.length"
        title="还没有评论"
        description="去世界那么大和作者聊两句，你的留言会出现在这里。"
        action-text="去逛逛"
        @action="router.push({ name: 'feed' })"
      />

      <ul v-else class="list">
        <li v-for="cmt in myComments" :key="cmt.id" class="cmt-item">
          <div class="cover" @click="openPost(cmt.post_id)">
            <img
              v-if="cmt.post_cover && !failedCovers[cmt.id]"
              :src="cmt.post_cover"
              :alt="cmt.post_title"
              loading="lazy"
              @error="markCoverFailed(cmt.id)"
            />
            <span v-else class="cover-fallback">{{ (cmt.post_city || '旅行').slice(0, 2) }}</span>
          </div>
          <div class="cmt-main" @click="openPost(cmt.post_id)">
            <p class="cmt-content">{{ cmt.content }}</p>
            <div class="cmt-meta">
              <span class="cmt-post">@ {{ cmt.post_title }}</span>
              <span>·</span>
              <span>{{ formatDateTime(cmt.created_at) }}</span>
            </div>
          </div>
          <button class="btn btn-quiet btn-sm" type="button" title="删除留言" @click.stop="removeComment(cmt)">
            <AppIcon name="trash" :size="14" />
          </button>
        </li>
      </ul>
    </section>

    <!-- Token 用量 -->
    <section v-else class="card section">
      <header class="section-head">
        <div>
          <h2>Token 用量</h2>
          <span class="muted">{{ usage?.date || '-' }} · 超过提醒阈值会自动给你发一条消息</span>
        </div>
      </header>

      <div v-if="loadingUsage" class="usage-skeleton">
        <div class="skeleton" style="height: 18px; width: 40%" />
        <div class="skeleton" style="height: 10px; width: 100%" />
      </div>

      <template v-else-if="usage">
        <div class="usage-top">
          <span class="usage-used">{{ formatNumber(usage.used_tokens) }}</span>
          <span class="muted">/ {{ formatNumber(usage.quota) }} tokens</span>
          <span class="usage-ratio">{{ usageRatio }}%</span>
        </div>
        <div class="usage-track">
          <div
            class="usage-fill"
            :class="{ 'is-warn': usageRatio >= Math.round(warnRatio * 100) }"
            :style="{ width: `${usageRatio}%` }"
          />
        </div>
        <div class="usage-foot">
          <span>已用 {{ formatNumber(usage.used_tokens) }}</span>
          <span>剩余 {{ formatNumber(usage.remaining) }}</span>
          <span>提醒阈值 {{ Math.round(warnRatio * 100) }}%（约 {{ formatNumber(usage.warn_tokens || 0) }}）</span>
        </div>

        <div class="warn-block">
          <label class="field">
            <span class="field-label">提醒阈值（占每日配额比例）</span>
            <input v-model.number="warnRatio" class="input" type="number" min="0.1" max="1" step="0.05" />
          </label>
          <button class="btn btn-primary btn-sm" type="button" :disabled="savingWarn" @click="saveWarnRatio">
            <span v-if="savingWarn" class="spinner" />
            保存阈值
          </button>
          <span class="hint-line muted">设为 0.8 表示用量达到 80% 时提醒一次（每天最多一次）</span>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.messages {
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

.tabs {
  display: flex;
  gap: 6px;
  padding: 8px;
  flex-wrap: wrap;
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
}

.tab:hover {
  background: #f5f6f8;
  color: var(--text);
}

.tab.is-active {
  background: var(--primary-soft);
  color: var(--primary-strong);
  font-weight: 600;
}

.tab-dot {
  display: inline-grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
}

.section {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.section-head h2,
.section-head h3 {
  font-size: 15px;
  font-weight: 600;
}

.section-head .muted {
  display: block;
  margin-top: 4px;
  font-size: 12.5px;
}

.sub-head {
  margin-top: 6px;
}

.head-actions {
  display: flex;
  gap: 8px;
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

.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 11px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  color: var(--text-muted);
  font-size: 12.5px;
  cursor: pointer;
}

.chip.is-on {
  border-color: var(--primary);
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.chip-count {
  color: #ef4444;
  font-weight: 600;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.msg-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 11px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--panel-soft);
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.msg-item:hover {
  border-color: #d8dee8;
  background: #fff;
}

.msg-item.is-unread {
  background: rgba(37, 99, 235, 0.06);
  border-color: #c8d6f5;
}

.kind-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 12px;
  background: #eef1f5;
  color: var(--text-muted);
}

.kind-token {
  background: var(--warning-soft);
  color: var(--warning);
}

.kind-collect {
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.msg-main {
  flex: 1;
  min-width: 0;
}

.msg-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.msg-title {
  font-size: 13.5px;
  font-weight: 600;
}

.msg-kind {
  padding: 1px 7px;
  border-radius: 999px;
  background: #f1f3f6;
  color: var(--text-faint);
  font-size: 11px;
}

.msg-content {
  margin-top: 3px;
  font-size: 12.5px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.msg-time {
  display: block;
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--text-faint);
}

.friend-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--panel-soft);
}

.friend-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.friend-main.is-link {
  cursor: pointer;
}

.friend-main.is-link:hover .friend-name {
  color: var(--primary-strong);
}

.friend-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13.5px;
  font-weight: 600;
}

.mutual {
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary-strong);
  font-size: 10.5px;
}

/* 单向关注：等待对方回关 */
.pending {
  padding: 1px 6px;
  border-radius: 999px;
  background: #f1f4f9;
  color: var(--text-muted);
  font-size: 10.5px;
}

.friend-bio {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hint-line {
  font-size: 12.5px;
}

.coll-item,
.cmt-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--panel-soft);
  cursor: pointer;
}

.coll-item:hover,
.cmt-item:hover {
  border-color: #d8dee8;
  background: #fff;
}

.cover {
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

.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-fallback {
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.coll-main,
.cmt-main {
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

.cmt-content {
  font-size: 13.5px;
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.cmt-meta {
  display: flex;
  align-items: center;
  gap: 6px;
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
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12.5px;
  color: var(--text-muted);
}

.warn-block {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
  padding: 14px;
  border-radius: 12px;
  background: var(--panel-soft);
  border: 1px dashed var(--border);
}

.warn-block .field {
  min-width: 220px;
}

@media (max-width: 620px) {
  .cmt-post {
    max-width: 150px;
  }

  .warn-block .field {
    min-width: 0;
    width: 100%;
  }
}
</style>
