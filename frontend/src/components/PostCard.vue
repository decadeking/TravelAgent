<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import UserAvatar from './UserAvatar.vue'
import type { PostSummary } from '@/types'

const props = defineProps<{ post: PostSummary }>()
const emit = defineEmits<{
  (e: 'open', post: PostSummary): void
  (e: 'like', post: PostSummary): void
  (e: 'collect', post: PostSummary): void
}>()

const router = useRouter()

/** 点击作者（头像或昵称）进入其主页，阻止冒泡以免触发卡片本身的「打开动态」 */
function openAuthor(event: MouseEvent) {
  const id = props.post.author?.id
  if (!id) return
  event.stopPropagation()
  router.push({ name: 'user-profile', params: { id } })
}

const cover = computed(() => props.post.images?.[0] ?? '')
const loaded = ref(false)
const errored = ref(false)

// 非公开动态在卡片上标注范围，提醒作者这条内容的可见边界
const VIS_LABELS: Record<string, string> = { friends: '好友可见', private: '仅自己可见' }
const visLabel = computed(() => VIS_LABELS[props.post.visibility] ?? '')

// 图片不可用时（离线/外链被墙）用城市主题渐变占位，保证观感
const GRADIENTS = [
  'linear-gradient(135deg,#6366f1 0%,#3b82f6 100%)',
  'linear-gradient(135deg,#0ea5e9 0%,#22d3ee 100%)',
  'linear-gradient(135deg,#f59e0b 0%,#f97316 100%)',
  'linear-gradient(135deg,#10b981 0%,#34d399 100%)',
  'linear-gradient(135deg,#8b5cf6 0%,#d946ef 100%)',
  'linear-gradient(135deg,#ef4444 0%,#f97316 100%)',
]
const fallbackStyle = computed(() => {
  const key = props.post.city || props.post.title || 'travel'
  let h = 0
  for (let i = 0; i < key.length; i += 1) h = (h * 31 + key.charCodeAt(i)) % 997
  return { background: GRADIENTS[h % GRADIENTS.length] }
})
</script>

<template>
  <article class="post-card" @click="emit('open', post)">
    <div class="cover" :class="{ 'is-empty': !cover }">
      <div v-if="!loaded && cover && !errored" class="skeleton cover-skeleton" />
      <img
        v-if="cover && !errored"
        :src="cover"
        :alt="post.title"
        loading="lazy"
        @load="loaded = true"
        @error="errored = true"
      />
      <div v-else class="cover-fallback" :style="fallbackStyle">
        <span class="fallback-city">{{ post.city || '旅行风光' }}</span>
        <span class="fallback-hint">{{ post.location || 'Travel moments' }}</span>
      </div>
    </div>

    <div class="body">
      <div class="title-row">
        <h3 class="title">{{ post.title }}</h3>
        <span v-if="visLabel" class="vis-badge">{{ visLabel }}</span>
      </div>
      <p class="place">
        <AppIcon name="map-pin" :size="13" />
        <span>{{ post.city }}</span>
        <template v-if="post.location">
          <span class="sep">·</span>
          <span class="loc">{{ post.location }}</span>
        </template>
      </p>
      <p v-if="post.excerpt" class="excerpt">{{ post.excerpt }}</p>

      <div v-if="post.tags?.length" class="tags">
        <span v-for="tag in post.tags.slice(0, 3)" :key="tag" class="tag tag-soft">#{{ tag }}</span>
      </div>

      <div class="foot">
        <div class="author" @click="openAuthor">
          <UserAvatar
            :src="post.author?.avatar"
            :name="post.author?.nickname"
            :size="24"
            :radius="12"
            :user-id="post.author?.id"
          />
          <span class="author-name">{{ post.author?.nickname || '旅行者' }}</span>
        </div>
        <div class="actions">
          <button
            class="act"
            :class="{ 'is-active': post.liked }"
            type="button"
            title="点赞"
            @click.stop="emit('like', post)"
          >
            <AppIcon name="heart" :size="15" :fill="post.liked ? 'currentColor' : 'none'" />
            <span>{{ post.like_count }}</span>
          </button>
          <button
            class="act"
            :class="{ 'is-star': post.collected }"
            type="button"
            title="收藏"
            @click.stop="emit('collect', post)"
          >
            <AppIcon name="star" :size="15" :fill="post.collected ? 'currentColor' : 'none'" />
            <span>{{ post.collect_count }}</span>
          </button>
          <span class="act act-static" title="评论">
            <AppIcon name="message" :size="15" />
            <span>{{ post.comment_count }}</span>
          </span>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.post-card {
  break-inside: avoid;
  margin-bottom: 16px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.post-card:hover {
  transform: translateY(-3px);
  border-color: #dbe3ef;
  box-shadow: 0 10px 26px rgba(17, 24, 39, 0.1);
}

.cover {
  position: relative;
  width: 100%;
  background: #f1f3f6;
}

.cover img {
  display: block;
  width: 100%;
  height: auto;
  max-height: 360px;
  object-fit: cover;
}

.cover.is-empty {
  aspect-ratio: 4 / 3;
}

.cover-skeleton {
  position: absolute;
  inset: 0;
  border-radius: 0;
}

.cover-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 100%;
  min-height: 168px;
  aspect-ratio: 4 / 3;
  color: #fff;
  text-align: center;
}

.fallback-city {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 3px;
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.18);
}

.fallback-hint {
  font-size: 12px;
  opacity: 0.86;
  letter-spacing: 0.5px;
}

.body {
  padding: 14px 16px 15px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.title-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.title-row .title {
  flex: 1;
  min-width: 0;
}

/* 可见范围标识：好友可见 / 仅自己可见 */
.vis-badge {
  flex-shrink: 0;
  margin-top: 2px;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid #d8e0ec;
  background: #f6f8fb;
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1.6;
}

.title {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.place {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.place .sep {
  color: var(--text-faint);
}

.place .loc {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.excerpt {
  font-size: 12.5px;
  color: var(--text-muted);
  line-height: 1.65;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px solid var(--border-soft);
}

.author {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  cursor: pointer;
}

.author:hover .author-name {
  color: var(--primary-strong);
}

.author-name {
  font-size: 12.5px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.act {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-faint);
  font-size: 12px;
  transition: background 0.14s ease, color 0.14s ease;
}

.act:hover {
  background: #f4f5f7;
  color: var(--text-muted);
}

.act.is-active {
  color: #e11d48;
}

.act.is-star {
  color: #f59e0b;
}

.act-static {
  cursor: default;
}
</style>
