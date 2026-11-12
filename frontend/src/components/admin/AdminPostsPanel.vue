<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/http'
import { formatDateTime } from '@/utils/format'
import type { PostSummary } from '@/types'

const status = ref('')
const visibility = ref('')
const page = ref(1)
const pageSize = 10
const items = ref<PostSummary[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')
const flash = ref('')
const busyId = ref<number | null>(null)

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'published', label: '已发布' },
  { value: 'pending', label: '待审核' },
  { value: 'rejected', label: '已下架' },
]

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  published: { label: '已发布', cls: 'tag-confirmed' },
  pending: { label: '待审核', cls: 'tag-draft' },
  rejected: { label: '已下架', cls: 'tag-rejected' },
  draft: { label: '草稿', cls: 'tag-draft' },
}

// 可见范围筛选与用户端发帖三档保持一致
const VIS_OPTIONS = [
  { value: '', label: '全部范围' },
  { value: 'public', label: '全部可见' },
  { value: 'friends', label: '好友可见' },
  { value: 'private', label: '仅自己可见' },
]

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// 可见范围标签：管理员审核时需知道内容对谁可见（与用户端文案保持一致）
const VIS_MAP: Record<string, string> = {
  friends: '好友可见',
  private: '仅自己可见',
}

function statusMeta(value: string) {
  return STATUS_MAP[value] ?? { label: value || '未知', cls: 'tag-soft' }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await adminApi.posts({
      status: status.value || undefined,
      visibility: visibility.value || undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = res.items
    total.value = res.total
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载内容失败'
  } finally {
    loading.value = false
  }
}

function notify(text: string) {
  flash.value = text
  window.setTimeout(() => {
    flash.value = ''
  }, 2600)
}

async function setStatus(post: PostSummary, next: string) {
  busyId.value = post.id
  error.value = ''
  try {
    await adminApi.setPostStatus(post.id, next)
    notify(`已${next === 'rejected' ? '下架' : '通过'}「${post.title}」`)
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
  } finally {
    busyId.value = null
  }
}

async function removePost(post: PostSummary) {
  if (!window.confirm(`确认删除动态「${post.title}」？该操作不可撤销。`)) return
  busyId.value = post.id
  try {
    await adminApi.removePost(post.id)
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
    notify('已删除该动态')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  } finally {
    busyId.value = null
  }
}

function changePage(next: number) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
}

watch(status, () => {
  page.value = 1
  load()
})

watch(visibility, () => {
  page.value = 1
  load()
})

onMounted(load)
</script>

<template>
  <div class="panel">
    <header class="panel-head">
      <div>
        <h3>内容审核</h3>
        <p>共 {{ total }} 条动态，可下架、通过或删除。</p>
      </div>
      <div class="head-filters">
        <select v-model="status" class="select" style="width: 140px">
          <option v-for="opt in STATUS_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <select v-model="visibility" class="select" style="width: 140px">
          <option v-for="opt in VIS_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
    </header>

    <div v-if="error" class="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
    </div>
    <div v-if="flash" class="alert is-ok">
      <AppIcon name="check" :size="14" />
      <span>{{ flash }}</span>
    </div>

    <div v-if="loading" class="rows">
      <div v-for="i in 5" :key="i" class="skeleton" style="height: 58px" />
    </div>

    <p v-else-if="!items.length" class="empty-tip">暂无符合条件的内容。</p>

    <div v-else class="rows">
      <article v-for="post in items" :key="post.id" class="row">
        <div class="row-cover">
          <img v-if="post.images?.[0]" :src="post.images[0]" :alt="post.title" loading="lazy" />
          <AppIcon v-else name="image" :size="18" />
        </div>
        <div class="row-main">
          <div class="row-title">
            <span class="row-post-title">{{ post.title }}</span>
            <span class="tag" :class="statusMeta(post.status).cls">{{ statusMeta(post.status).label }}</span>
            <span v-if="VIS_MAP[post.visibility]" class="tag tag-soft">{{ VIS_MAP[post.visibility] }}</span>
          </div>
          <div class="row-meta">
            <UserAvatar
              :src="post.author?.avatar"
              :name="post.author?.nickname"
              :size="18"
              :radius="9"
              :user-id="post.author?.id"
            />
            <span>{{ post.author?.nickname || '旅行者' }}</span>
            <span class="meta-sep">·</span>
            <span>{{ post.city }}</span>
            <span class="meta-sep">·</span>
            <span>{{ formatDateTime(post.created_at) }}</span>
          </div>
          <div class="row-stats">
            <span class="heat-chip"><AppIcon name="zap" :size="12" /> {{ post.heat }}</span>
            <span><AppIcon name="heart" :size="12" /> {{ post.like_count }}</span>
            <span><AppIcon name="star" :size="12" /> {{ post.collect_count }}</span>
            <span><AppIcon name="message" :size="12" /> {{ post.comment_count }}</span>
          </div>
        </div>
        <div class="row-actions">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :disabled="busyId === post.id || post.status === 'published'"
            @click="setStatus(post, 'published')"
          >
            通过
          </button>
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :disabled="busyId === post.id || post.status === 'rejected'"
            @click="setStatus(post, 'rejected')"
          >
            下架
          </button>
          <button class="btn btn-danger btn-sm" type="button" :disabled="busyId === post.id" @click="removePost(post)">
            删除
          </button>
        </div>
      </article>
    </div>

    <div v-if="totalPages > 1" class="pager">
      <button class="btn btn-ghost btn-sm" type="button" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
      <span class="pager-text">第 {{ page }} / {{ totalPages }} 页</span>
      <button class="btn btn-ghost btn-sm" type="button" :disabled="page >= totalPages" @click="changePage(page + 1)">
        下一页
      </button>
    </div>
  </div>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.panel-head h3 {
  font-size: 15.5px;
  font-weight: 650;
}

.panel-head p {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--text-muted);
}

/* 审核筛选：状态 + 可见范围，与用户端三档口径一致 */
.head-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.alert {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 13px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.alert.is-ok {
  background: var(--success-soft);
  color: var(--success);
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
  transition: border-color 0.16s ease;
}

.row:hover {
  border-color: #d8dee8;
}

.row-cover {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: 10px;
  overflow: hidden;
  background: #f1f3f6;
  color: var(--text-faint);
}

.row-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.row-main {
  flex: 1;
  min-width: 0;
}

.row-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-post-title {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  font-size: 12px;
  color: var(--text-muted);
}

.meta-sep {
  color: var(--text-faint);
}

.row-stats {
  display: flex;
  gap: 14px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-faint);
}

.row-stats span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.heat-chip {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--warning-soft);
  color: var(--warning);
  font-weight: 600;
}

.row-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.tag-rejected {
  background: var(--danger-soft);
  color: var(--danger);
}

.empty-tip {
  padding: 32px;
  text-align: center;
  font-size: 13px;
  color: var(--text-faint);
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
}

.pager-text {
  font-size: 12.5px;
  color: var(--text-muted);
}

@media (max-width: 720px) {
  .row {
    flex-wrap: wrap;
  }

  .row-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
