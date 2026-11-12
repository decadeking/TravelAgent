<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import PostCard from '@/components/PostCard.vue'
import PostFormDialog from '@/components/PostFormDialog.vue'
import { ApiError } from '@/api/http'
import { postApi } from '@/api/posts'
import type { CityChip, PostPayload, PostSummary } from '@/types'

const router = useRouter()

const posts = ref<PostSummary[]>([])
const cities = ref<CityChip[]>([])
const city = ref('')
const sort = ref<'new' | 'hot'>('new')
const page = ref(1)
const pageSize = 12
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')

const showForm = ref(false)
const saving = ref(false)

const canLoadMore = ref(false)

async function loadCities() {
  try {
    cities.value = await postApi.cities()
  } catch {
    /* 城市筛选失败不影响主列表 */
  }
}

async function loadPosts(reset = true) {
  if (reset) {
    loading.value = true
    page.value = 1
  } else {
    loadingMore.value = true
  }
  error.value = ''
  try {
    const res = await postApi.list({
      page: page.value,
      page_size: pageSize,
      city: city.value || undefined,
      sort: sort.value,
    })
    posts.value = reset ? res.items : [...posts.value, ...res.items]
    total.value = res.total
    canLoadMore.value = posts.value.length < res.total
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载动态失败'
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function loadMore() {
  if (!canLoadMore.value || loadingMore.value) return
  page.value += 1
  loadPosts(false)
}

function selectCity(value: string) {
  if (city.value === value) return
  city.value = value
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

async function submitPost(payload: PostPayload) {
  saving.value = true
  error.value = ''
  try {
    await postApi.create(payload)
    showForm.value = false
    await loadPosts(true)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '发布失败'
  } finally {
    saving.value = false
  }
}

watch([city, sort], () => loadPosts(true))

onMounted(() => {
  loadCities()
  loadPosts(true)
})
</script>

<template>
  <div class="feed">
    <header class="page-head">
      <!-- 左上角「世界那么大」由顶部标题栏统一展示，这里只保留说明文字 -->
      <p class="page-desc">发现旅行者的真实足迹与灵感，也分享属于你的旅途故事。</p>
      <button class="btn btn-primary" type="button" @click="showForm = true">
        <AppIcon name="plus" :size="16" />
        发布动态
      </button>
    </header>

    <div class="filter-bar">
      <div class="chips">
        <button class="chip" :class="{ 'is-active': city === '' }" type="button" @click="selectCity('')">
          全部
        </button>
        <button
          v-for="item in cities"
          :key="item.city"
          class="chip"
          :class="{ 'is-active': city === item.city }"
          type="button"
          @click="selectCity(item.city)"
        >
          {{ item.city }}
          <span class="chip-count">{{ item.count }}</span>
        </button>
      </div>
      <div class="segmented">
        <button type="button" :class="{ 'is-active': sort === 'new' }" @click="sort = 'new'">最新</button>
        <button type="button" :class="{ 'is-active': sort === 'hot' }" @click="sort = 'hot'">最热</button>
      </div>
    </div>

    <div v-if="error" class="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
    </div>

    <div v-if="loading" class="waterfall">
      <div v-for="i in 6" :key="i" class="skeleton-card card">
        <div class="skeleton" style="height: 170px" />
        <div class="skeleton" style="height: 16px; width: 80%; margin: 12px 14px 0" />
        <div class="skeleton" style="height: 13px; width: 50%; margin: 8px 14px 16px" />
      </div>
    </div>

    <EmptyState
      v-else-if="!posts.length"
      title="这里还没有动态"
      description="成为第一个分享旅行见闻的人，记录你的行程与美好瞬间。"
      action-text="发布动态"
      @action="showForm = true"
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

    <PostFormDialog v-if="showForm" :saving="saving" @submit="submitPost" @close="showForm = false" />
  </div>
</template>

<style scoped>
.feed {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 1180px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

/* 说明文字作为页头主文案：与「个人行程」页保持一致（放大、左对齐） */
.page-desc {
  flex: 1;
  min-width: 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--text);
  letter-spacing: 0.1px;
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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
}
</style>
