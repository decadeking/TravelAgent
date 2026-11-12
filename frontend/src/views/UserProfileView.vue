<script setup lang="ts">
/**
 * 他人（或自己）的公开主页：/u/:id
 * - 展示头像 / 昵称 / 简介 / 动态·关注·粉丝 三项统计
 * - 关注 / 取关（关注即好友）；访问自己的主页时不显示关注按钮
 * - 下方按瀑布流展示 TA 发布的动态，点击进入动态详情
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import PostCard from '@/components/PostCard.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { ApiError } from '@/api/http'
import { postApi } from '@/api/posts'
import { userApi } from '@/api/users'
import type { PostSummary, UserPublic } from '@/types'

const route = useRoute()
const router = useRouter()

const userId = computed(() => Number(route.params.id))

const profile = ref<UserPublic | null>(null)
const posts = ref<PostSummary[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 12

const loading = ref(true)
const loadingPosts = ref(false)
const loadingMore = ref(false)
const busyFollow = ref(false)
const error = ref('')

const canLoadMore = computed(() => posts.value.length < total.value)

const stats = computed(() => [
  { key: 'posts', label: '动态', value: total.value },
  { key: 'following', label: '关注', value: profile.value?.following_count ?? 0 },
  { key: 'followers', label: '粉丝', value: profile.value?.followers ?? 0 },
])

async function loadProfile() {
  loading.value = true
  error.value = ''
  try {
    profile.value = await userApi.userProfile(userId.value)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载用户资料失败'
  } finally {
    loading.value = false
  }
}

async function loadPosts(reset = true) {
  if (reset) {
    loadingPosts.value = true
    page.value = 1
  } else {
    loadingMore.value = true
  }
  try {
    const res = await postApi.list({
      page: page.value,
      page_size: pageSize,
      author_id: userId.value,
    })
    posts.value = reset ? res.items : [...posts.value, ...res.items]
    total.value = res.total
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载动态失败'
  } finally {
    loadingPosts.value = false
    loadingMore.value = false
  }
}

function loadMore() {
  if (!canLoadMore.value || loadingMore.value) return
  page.value += 1
  loadPosts(false)
}

async function toggleFollow() {
  if (!profile.value || busyFollow.value) return
  busyFollow.value = true
  error.value = ''
  const prev = { following: profile.value.following, followers: profile.value.followers }
  // 乐观更新：先改 UI，失败再回滚
  profile.value.following = !prev.following
  profile.value.followers = prev.followers + (prev.following ? -1 : 1)
  try {
    const res = await userApi.toggleFollow(profile.value.id)
    profile.value.following = res.following
    profile.value.followers = prev.followers + (res.following ? 1 : -1)
  } catch (err) {
    profile.value.following = prev.following
    profile.value.followers = prev.followers
    error.value = err instanceof ApiError ? err.message : '操作失败'
  } finally {
    busyFollow.value = false
  }
}

function openPost(post: PostSummary) {
  router.push({ name: 'post-detail', params: { id: post.id } })
}

async function toggleLike(post: PostSummary) {
  const target = posts.value.find((item) => item.id === post.id)
  if (!target) return
  target.liked = !target.liked
  target.like_count += target.liked ? 1 : -1
  try {
    const res = await postApi.like(post.id)
    target.liked = res.liked
    target.like_count = res.like_count
  } catch (err) {
    target.liked = !target.liked
    target.like_count += target.liked ? 1 : -1
    error.value = err instanceof ApiError ? err.message : '操作失败'
  }
}

async function toggleCollect(post: PostSummary) {
  const target = posts.value.find((item) => item.id === post.id)
  if (!target) return
  target.collected = !target.collected
  target.collect_count += target.collected ? 1 : -1
  try {
    const res = await postApi.collect(post.id)
    target.collected = res.collected
    target.collect_count = res.collect_count
  } catch (err) {
    target.collected = !target.collected
    target.collect_count += target.collected ? 1 : -1
    error.value = err instanceof ApiError ? err.message : '操作失败'
  }
}

function reload() {
  loadProfile()
  loadPosts(true)
}

watch(userId, reload, { immediate: true })
</script>

<template>
  <div class="user-page">
    <button class="btn btn-quiet btn-sm back" type="button" @click="router.back()">
      <AppIcon name="arrow-left" :size="15" />
      返回
    </button>

    <div v-if="error" class="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
    </div>

    <!-- 资料卡 -->
    <section class="card profile-card">
      <div v-if="loading" class="profile-skeleton">
        <div class="skeleton" style="width: 72px; height: 72px; border-radius: 22px" />
        <div class="skeleton" style="height: 18px; width: 160px" />
        <div class="skeleton" style="height: 13px; width: 260px" />
      </div>

      <template v-else-if="profile">
        <div class="profile-main">
          <UserAvatar :src="profile.avatar" :name="profile.nickname" :size="72" :radius="22" />
          <div class="profile-info">
            <div class="name-row">
              <h1 class="profile-name">{{ profile.nickname }}</h1>
              <span v-if="profile.is_friend && !profile.is_me" class="tag tag-soft">好友</span>
            </div>
            <span class="profile-username">@{{ profile.username }}</span>
            <p class="profile-bio">{{ profile.bio || '这位旅行者还没有填写简介～' }}</p>
          </div>

          <div class="profile-actions">
            <template v-if="profile.is_me">
              <span class="self-hint">这是你的主页</span>
              <button class="btn btn-ghost btn-sm" type="button" @click="router.push({ name: 'profile' })">
                <AppIcon name="edit" :size="14" />
                编辑资料
              </button>
            </template>
            <button
              v-else
              class="btn btn-sm"
              :class="profile.following ? 'btn-ghost' : 'btn-primary'"
              type="button"
              :disabled="busyFollow"
              @click="toggleFollow"
            >
              <span v-if="busyFollow" class="spinner" :class="{ 'spinner-dark': profile.following }" />
              <AppIcon v-else :name="profile.following ? 'check' : 'plus'" :size="15" />
              {{ profile.following ? '已关注' : '关注' }}
            </button>
          </div>
        </div>

        <div class="stats">
          <div v-for="item in stats" :key="item.key" class="stat">
            <span class="stat-value">{{ item.value }}</span>
            <span class="stat-label">{{ item.label }}</span>
          </div>
        </div>
      </template>

      <EmptyState
        v-else
        title="用户不存在"
        description="该用户可能已注销或不存在。"
        action-text="返回世界那么大"
        @action="router.push({ name: 'feed' })"
      />
    </section>

    <!-- TA 的动态 -->
    <template v-if="profile">
      <header class="section-head">
        <h2>{{ profile.is_me ? '我的动态' : `${profile.nickname} 的动态` }}</h2>
        <span class="muted">{{ total }} 条</span>
      </header>

      <div v-if="loadingPosts" class="waterfall">
        <div v-for="i in 4" :key="i" class="skeleton-card card">
          <div class="skeleton" style="height: 170px" />
          <div class="skeleton" style="height: 16px; width: 80%; margin: 12px 14px 0" />
          <div class="skeleton" style="height: 13px; width: 50%; margin: 8px 14px 16px" />
        </div>
      </div>

      <EmptyState
        v-else-if="!posts.length"
        title="还没有发布动态"
        description="TA 还没有分享过旅途故事。"
        action-text="返回世界那么大"
        @action="router.push({ name: 'feed' })"
      />

      <template v-else>
        <div class="waterfall">
          <PostCard
            v-for="post in posts"
            :key="post.id"
            :post="post"
            @open="openPost"
            @like="toggleLike"
            @collect="toggleCollect"
          />
        </div>

        <div v-if="canLoadMore" class="load-more">
          <button class="btn btn-ghost" type="button" :disabled="loadingMore" @click="loadMore">
            <span v-if="loadingMore" class="spinner spinner-dark" />
            {{ loadingMore ? '加载中…' : '加载更多' }}
          </button>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.user-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 1180px;
  margin: 0 auto;
}

.back {
  align-self: flex-start;
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

.profile-card {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 22px;
}

.profile-skeleton {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.profile-main {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.profile-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.profile-name {
  font-size: 20px;
  font-weight: 650;
}

.profile-username {
  font-size: 12.5px;
  color: var(--text-faint);
}

.profile-bio {
  margin-top: 3px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-muted);
  white-space: pre-wrap;
  word-break: break-word;
}

.profile-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.self-hint {
  font-size: 12.5px;
  color: var(--text-faint);
}

.stats {
  display: flex;
  gap: 28px;
  padding-top: 16px;
  border-top: 1px solid var(--border-soft);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--primary-strong);
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.section-head h2 {
  font-size: 16px;
  font-weight: 650;
}

.waterfall {
  column-count: 2;
  column-gap: 16px;
}

.skeleton-card {
  break-inside: avoid;
  margin-bottom: 16px;
  padding-bottom: 14px;
  overflow: hidden;
}

.skeleton-card .skeleton {
  border-radius: 0;
}

.load-more {
  display: flex;
  justify-content: center;
  padding: 4px 0 8px;
}

@media (max-width: 720px) {
  .waterfall {
    column-count: 1;
  }

  .profile-main {
    flex-wrap: wrap;
  }

  .profile-actions {
    width: 100%;
  }

  .stats {
    gap: 20px;
  }
}
</style>
