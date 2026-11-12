<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import PostFormDialog from '@/components/PostFormDialog.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { ApiError } from '@/api/http'
import { postApi } from '@/api/posts'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'
import type { PostDetail, PostPayload } from '@/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const post = ref<PostDetail | null>(null)
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const showEdit = ref(false)
const commentText = ref('')
const commenting = ref(false)

const postId = computed(() => Number(route.params.id))

const isOwner = computed(() => Boolean(post.value && auth.user && post.value.author?.id === auth.user.id))
// 自己的动态显示可见范围，与发帖时的选择保持一致的文案
const visLabel = computed(() => {
  const v = post.value?.visibility
  return v === 'friends' ? '好友可见' : v === 'private' ? '仅自己可见' : ''
})
const canManage = computed(() => isOwner.value || auth.isAdmin)

const images = computed(() => post.value?.images ?? [])
const tags = computed(() => post.value?.tags ?? [])

/** 点击头像 / 昵称进入该用户主页 */
function openUser(id?: number) {
  if (!id) return
  router.push({ name: 'user-profile', params: { id } })
}

const failedImages = ref<Record<number, boolean>>({})
const GALLERY_GRADIENTS = [
  'linear-gradient(135deg,#6366f1,#3b82f6)',
  'linear-gradient(135deg,#0ea5e9,#22d3ee)',
  'linear-gradient(135deg,#f59e0b,#f97316)',
  'linear-gradient(135deg,#10b981,#34d399)',
  'linear-gradient(135deg,#8b5cf6,#d946ef)',
  'linear-gradient(135deg,#ef4444,#f97316)',
]

function galleryStyle(seed: string) {
  let h = 0
  const key = seed || 'travel'
  for (let i = 0; i < key.length; i += 1) h = (h * 31 + key.charCodeAt(i)) % 997
  return { background: GALLERY_GRADIENTS[h % GALLERY_GRADIENTS.length] }
}

function markImageFailed(index: number) {
  failedImages.value[index] = true
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    post.value = await postApi.detail(postId.value)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载动态失败'
  } finally {
    loading.value = false
  }
}

async function toggleLike() {
  if (!post.value) return
  post.value.liked = !post.value.liked
  post.value.like_count += post.value.liked ? 1 : -1
  try {
    const res = await postApi.like(post.value.id)
    post.value.liked = res.liked
    post.value.like_count = res.like_count
  } catch (err) {
    if (post.value) {
      post.value.liked = !post.value.liked
      post.value.like_count += post.value.liked ? 1 : -1
    }
    error.value = err instanceof ApiError ? err.message : '操作失败'
  }
}

async function toggleCollect() {
  if (!post.value) return
  post.value.collected = !post.value.collected
  post.value.collect_count += post.value.collected ? 1 : -1
  try {
    const res = await postApi.collect(post.value.id)
    post.value.collected = res.collected
    post.value.collect_count = res.collect_count
  } catch (err) {
    if (post.value) {
      post.value.collected = !post.value.collected
      post.value.collect_count += post.value.collected ? 1 : -1
    }
    error.value = err instanceof ApiError ? err.message : '操作失败'
  }
}

async function submitComment() {
  const content = commentText.value.trim()
  if (!content || !post.value || commenting.value) return
  commenting.value = true
  error.value = ''
  try {
    const created = await postApi.comment(post.value.id, content)
    post.value.comments = [created, ...(post.value.comments ?? [])]
    post.value.comment_count += 1
    commentText.value = ''
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '留言失败'
  } finally {
    commenting.value = false
  }
}

async function removeComment(id: number) {
  if (!post.value) return
  if (!window.confirm('确认删除这条留言？')) return
  try {
    await postApi.removeComment(id)
    post.value.comments = post.value.comments.filter((item) => item.id !== id)
    post.value.comment_count = Math.max(0, post.value.comment_count - 1)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除留言失败'
  }
}

async function submitEdit(payload: PostPayload) {
  if (!post.value) return
  saving.value = true
  error.value = ''
  try {
    post.value = await postApi.update(post.value.id, payload)
    showEdit.value = false
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function removePost() {
  if (!post.value) return
  if (!window.confirm(`确认删除动态「${post.value.title}」？该操作不可撤销。`)) return
  try {
    await postApi.remove(post.value.id)
    router.replace({ name: 'feed' })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <div class="detail">
    <button class="btn btn-quiet btn-sm back" type="button" @click="router.push({ name: 'feed' })">
      <AppIcon name="arrow-left" :size="15" />
      返回世界那么大
    </button>

    <div v-if="loading" class="card loading-card">
      <div class="skeleton" style="height: 240px" />
      <div class="skeleton" style="height: 22px; width: 55%" />
      <div class="skeleton" style="height: 14px; width: 80%" />
    </div>

    <EmptyState
      v-else-if="!post"
      title="动态不存在"
      description="该内容可能已被删除或下架。"
      action-text="返回旅行吧"
      @action="router.push({ name: 'feed' })"
    />

    <template v-else>
      <div v-if="error" class="alert">
        <AppIcon name="alert" :size="14" />
        <span>{{ error }}</span>
      </div>

      <article class="card post">
        <div v-if="images.length" class="gallery" :class="`gallery-${Math.min(images.length, 3)}`">
          <template v-for="(img, i) in images.slice(0, 3)" :key="i">
            <img v-if="!failedImages[i]" :src="img" :alt="post.title" loading="lazy" @error="markImageFailed(i)" />
            <div v-else class="gallery-fallback" :style="galleryStyle(post.city || post.title)">
              <AppIcon name="image" :size="22" />
            </div>
          </template>
        </div>

        <div class="post-body">
          <div class="post-top">
            <div class="post-heading">
              <h1 class="post-title">{{ post.title }}</h1>
              <div class="post-meta">
                <span class="place">
                  <AppIcon name="map-pin" :size="14" />
                  {{ post.city }}<template v-if="post.location"> · {{ post.location }}</template>
                </span>
                <span class="meta-sep">·</span>
                <span>{{ formatDateTime(post.created_at) }}</span>
                <span class="meta-sep">·</span>
                <span class="views"><AppIcon name="eye" :size="13" /> {{ post.view_count }}</span>
              </div>
            </div>
            <div v-if="canManage" class="post-actions">
              <button class="btn btn-ghost btn-sm" type="button" @click="showEdit = true">
                <AppIcon name="edit" :size="14" />
                编辑
              </button>
              <button class="btn btn-danger btn-sm" type="button" @click="removePost">
                <AppIcon name="trash" :size="14" />
                删除
              </button>
            </div>
          </div>

          <div v-if="tags.length" class="tags">
            <span v-for="tag in tags" :key="tag" class="tag tag-soft">#{{ tag }}</span>
          </div>

          <div class="author-row">
            <UserAvatar
              :src="post.author?.avatar"
              :name="post.author?.nickname"
              :size="40"
              :radius="14"
              :user-id="post.author?.id"
            />
            <div class="author-info" @click="openUser(post.author?.id)">
              <span class="author-name">{{ post.author?.nickname || '旅行者' }}</span>
              <span class="author-sub">
                分享于世界那么大
                <span v-if="isOwner && visLabel" class="vis-tag">{{ visLabel }}</span>
              </span>
            </div>
          </div>

          <p class="post-content">{{ post.content }}</p>

          <div class="engage">
            <button class="engage-btn" :class="{ 'is-active': post.liked }" type="button" @click="toggleLike">
              <AppIcon name="heart" :size="17" :fill="post.liked ? 'currentColor' : 'none'" />
              <span>{{ post.like_count }}</span>
            </button>
            <button class="engage-btn" :class="{ 'is-star': post.collected }" type="button" @click="toggleCollect">
              <AppIcon name="star" :size="17" :fill="post.collected ? 'currentColor' : 'none'" />
              <span>{{ post.collect_count }}</span>
            </button>
            <span class="engage-btn engage-static">
              <AppIcon name="message" :size="17" />
              <span>{{ post.comment_count }}</span>
            </span>
          </div>
        </div>
      </article>

      <section class="card comments">
        <h3 class="comments-title">留言 ({{ post.comment_count }})</h3>

        <div class="comment-input">
          <UserAvatar :src="auth.user?.avatar" :name="auth.displayName" :size="34" :radius="12" />
          <textarea
            v-model="commentText"
            class="textarea"
            rows="2"
            placeholder="写下你的想法…"
            @keydown.enter.exact.prevent="submitComment"
          />
          <button class="btn btn-primary btn-sm" type="button" :disabled="commenting || !commentText.trim()" @click="submitComment">
            <span v-if="commenting" class="spinner" />
            发布
          </button>
        </div>

        <ul v-if="post.comments?.length" class="comment-list">
          <li v-for="item in post.comments" :key="item.id" class="comment">
            <UserAvatar
              :src="item.author?.avatar"
              :name="item.author?.nickname"
              :size="34"
              :radius="12"
              :user-id="item.user_id"
            />
            <div class="comment-body">
              <div class="comment-head">
                <span class="comment-name" @click="openUser(item.user_id)">
                  {{ item.author?.nickname || '旅行者' }}
                </span>
                <span class="comment-time">{{ formatDateTime(item.created_at) }}</span>
                <button
                  v-if="auth.isAdmin || item.user_id === auth.user?.id"
                  class="comment-del"
                  type="button"
                  @click="removeComment(item.id)"
                >
                  删除
                </button>
              </div>
              <p class="comment-text">{{ item.content }}</p>
            </div>
          </li>
        </ul>
        <p v-else class="comment-empty">还没有留言，来说点什么吧。</p>
      </section>
    </template>

    <PostFormDialog v-if="showEdit && post" :post="post" :saving="saving" @submit="submitEdit" @close="showEdit = false" />
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 860px;
  margin: 0 auto;
}

.back {
  align-self: flex-start;
}

.loading-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
}

.alert {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 13px;
}

.post {
  overflow: hidden;
}

.gallery {
  display: grid;
  gap: 2px;
  background: #eef1f5;
}

.gallery-1 {
  grid-template-columns: 1fr;
}

.gallery-2 {
  grid-template-columns: 1fr 1fr;
}

.gallery-3 {
  grid-template-columns: 2fr 1fr;
}

.gallery-3 img:first-child {
  grid-row: span 2;
}

.gallery img {
  width: 100%;
  height: 100%;
  max-height: 440px;
  object-fit: cover;
  display: block;
}

.gallery-fallback {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  min-height: 180px;
  max-height: 440px;
  color: #fff;
}

.gallery-3 .gallery-fallback:first-child {
  grid-row: span 2;
}

.post-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
}

.post-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.post-title {
  font-size: 21px;
  font-weight: 650;
  line-height: 1.45;
}

.post-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.post-meta .place {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.post-meta .views {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.meta-sep {
  color: var(--text-faint);
}

.post-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.author-row {
  display: flex;
  align-items: center;
  gap: 11px;
}

.author-info {
  cursor: pointer;
}

.author-info:hover .author-name {
  color: var(--primary-strong);
}

.author-name {
  font-size: 14px;
  font-weight: 600;
}

.author-sub {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-faint);
}

/* 可见范围：与发帖时选择一致的文案 */
.vis-tag {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid #dfe5ee;
  background: #f4f7fb;
  color: var(--text-muted);
  font-size: 10.5px;
}

.post-content {
  font-size: 14.5px;
  line-height: 1.9;
  color: #2b3038;
  white-space: pre-wrap;
  word-break: break-word;
}

.engage {
  display: flex;
  gap: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--border-soft);
}

.engage-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  color: var(--text-muted);
  font-size: 13px;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.engage-btn:hover {
  border-color: #d3d8e0;
  color: var(--text);
}

.engage-btn.is-active {
  color: #e11d48;
  border-color: #f7c9d3;
  background: #fff1f4;
}

.engage-btn.is-star {
  color: #d97706;
  border-color: #f6dcae;
  background: #fff8ec;
}

.engage-static {
  cursor: default;
}

.engage-static:hover {
  border-color: var(--border);
  color: var(--text-muted);
}

.comments {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 20px;
}

.comments-title {
  font-size: 15px;
  font-weight: 600;
}

.comment-input {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.comment-input .textarea {
  min-height: 44px;
}

.comment-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.comment {
  display: flex;
  gap: 10px;
}

.comment-body {
  flex: 1;
  min-width: 0;
}

.comment-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.comment-name {
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.comment-name:hover {
  color: var(--primary-strong);
}

.comment-time {
  font-size: 11.5px;
  color: var(--text-faint);
}

.comment-del {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--text-faint);
  font-size: 12px;
}

.comment-del:hover {
  color: var(--danger);
}

.comment-text {
  margin-top: 4px;
  font-size: 13.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.comment-empty {
  font-size: 13px;
  color: var(--text-faint);
}

@media (max-width: 640px) {
  .gallery-3 {
    grid-template-columns: 1fr 1fr;
  }

  .gallery-3 img:first-child {
    grid-row: auto;
    grid-column: span 2;
  }

  .post-top {
    flex-direction: column;
  }

  .comment-input {
    flex-wrap: wrap;
  }
}
</style>
