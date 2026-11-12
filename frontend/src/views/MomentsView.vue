<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import PostFormDialog from '@/components/PostFormDialog.vue'
import { mediaApi } from '@/api/media'
import { ApiError } from '@/api/http'
import { postApi } from '@/api/posts'
import { userApi } from '@/api/users'
import { formatDateTime } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'
import type { MomentPost, PostComment, PostDetail, PostPayload } from '@/types'

/**
 * 动态页（QQ 空间风格）：
 * 只看「我关注的人 + 我自己的动态」，自己的帖子与评论可就地增删改查，
 * 背景图点击即可上传，文件统一落在后端资源文件夹（/api/media/xx）。
 */
const router = useRouter()
const auth = useAuthStore()

const moments = ref<MomentPost[]>([])
const followingCount = ref(0)
const friendsCount = ref(0)
const followersCount = ref(0)
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(true)
const error = ref('')
const flash = ref('')
const busyId = ref<number | null>(null)

const showForm = ref(false)
const editing = ref<PostDetail | null>(null)
const savingPost = ref(false)
const coverInput = ref<HTMLInputElement | null>(null)
const uploadingCover = ref(false)

const commentsMap = reactive<Record<number, PostComment[]>>({})
const commentsOpen = reactive<Record<number, boolean>>({})
const commentLoading = reactive<Record<number, boolean>>({})
const commentDraft = reactive<Record<number, string>>({})
const editingCommentId = ref<number | null>(null)
const editingCommentText = ref('')
const failedImages = reactive<Record<string, boolean>>({})

const me = computed(() => auth.user)
/** 是否被管理员拉黑：拉黑后禁止发帖/点赞/评论/收藏（后端同样强制拦截） */
const isBanned = computed(() => Boolean(me.value?.banned))
const coverStyle = computed(() => {
  const cover = (me.value?.cover || '').trim()
  return cover ? { backgroundImage: `url(${cover})` } : {}
})

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
    const res = await postApi.moments({ page: page.value, page_size: pageSize })
    moments.value = res.items
    total.value = res.total
    followingCount.value = res.following_count
    friendsCount.value = res.friends_count ?? 0
    followersCount.value = res.followers_count ?? 0
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载动态失败'
  } finally {
    loading.value = false
  }
}

function isMine(post: MomentPost): boolean {
  return post.author?.id === me.value?.id
}

function postTime(post: MomentPost): string {
  return post.created_at ? formatDateTime(post.created_at) : ''
}

// ---- 个性备注（点击可改） ----
const editingBio = ref(false)
const bioDraft = ref('')
const bioInput = ref<HTMLInputElement | null>(null)

async function startBioEdit() {
  bioDraft.value = me.value?.bio || ''
  editingBio.value = true
  await nextTick()
  bioInput.value?.focus()
}

function cancelBio() {
  editingBio.value = false
}

async function saveBio() {
  if (!editingBio.value) return
  const next = bioDraft.value.trim()
  editingBio.value = false
  if (next === (me.value?.bio || '')) return          // 没有变化就不请求
  try {
    const updated = await userApi.updateMe({ bio: next })
    auth.setUser(updated)
    notify(next ? '个性备注已更新' : '个性备注已清空')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '个性备注保存失败'
  }
}

// ---- 背景图 ----
async function onCoverChange(event: Event) {
  const el = event.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  uploadingCover.value = true
  error.value = ''
  try {
    const res = await mediaApi.upload(file, 'image')
    const updated = await userApi.updateMe({ cover: res.url })
    auth.setUser(updated)
    notify('背景图已保存到后端资源文件夹')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '背景图上传失败'
  } finally {
    uploadingCover.value = false
  }
}

// ---- 帖子 ----
async function toggleLike(post: MomentPost) {
  try {
    const res = await postApi.like(post.id)
    post.liked = res.liked
    post.like_count = res.like_count
    if (typeof res.heat === 'number') post.heat = res.heat
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
  }
}

async function toggleCollect(post: MomentPost) {
  try {
    const res = await postApi.collect(post.id)
    post.collected = res.collected
    post.collect_count = res.collect_count
    if (typeof res.heat === 'number') post.heat = res.heat
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
  }
}

function openCreate() {
  if (isBanned.value) {
    error.value = '你的账号已被管理员加入黑名单，暂时无法发布动态'
    return
  }
  editing.value = null
  showForm.value = true
}

function openEdit(post: MomentPost) {
  editing.value = post as unknown as PostDetail
  showForm.value = true
}

async function submitPost(payload: PostPayload) {
  savingPost.value = true
  error.value = ''
  try {
    if (editing.value) {
      await postApi.update(editing.value.id, payload)
      notify('动态已更新')
    } else {
      await postApi.create(payload)
      notify('动态已发布')
    }
    showForm.value = false
    editing.value = null
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    savingPost.value = false
  }
}

async function removePost(post: MomentPost) {
  if (!window.confirm(`确认删除动态「${post.title || post.excerpt}」？`)) return
  busyId.value = post.id
  try {
    await postApi.remove(post.id)
    moments.value = moments.value.filter((p) => p.id !== post.id)
    total.value = Math.max(0, total.value - 1)
    notify('动态已删除')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  } finally {
    busyId.value = null
  }
}

// ---- 评论 ----
async function toggleComments(post: MomentPost) {
  const open = !commentsOpen[post.id]
  commentsOpen[post.id] = open
  if (open && !commentsMap[post.id]) {
    commentLoading[post.id] = true
    try {
      const detail = await postApi.detail(post.id)
      commentsMap[post.id] = detail.comments || []
      post.comment_count = detail.comment_count
    } catch (err) {
      error.value = err instanceof ApiError ? err.message : '加载留言失败'
    } finally {
      commentLoading[post.id] = false
    }
  }
}

async function submitComment(post: MomentPost) {
  const text = (commentDraft[post.id] || '').trim()
  if (!text) return
  try {
    const created = await postApi.comment(post.id, text)
    commentsMap[post.id] = [...(commentsMap[post.id] || []), created]
    commentDraft[post.id] = ''
    post.comment_count += 1
    post.heat += 1
    notify('留言已发布')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '留言失败'
  }
}

function startEditComment(c: PostComment) {
  editingCommentId.value = c.id
  editingCommentText.value = c.content
}

async function saveEditComment(post: MomentPost) {
  const id = editingCommentId.value
  if (id === null) return
  const text = editingCommentText.value.trim()
  if (!text) return
  try {
    await postApi.updateComment(id, text)
    const list = commentsMap[post.id] || []
    const target = list.find((c) => c.id === id)
    if (target) target.content = text
    editingCommentId.value = null
    editingCommentText.value = ''
    notify('留言已更新')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '更新留言失败'
  }
}

async function removeComment(post: MomentPost, comment: PostComment) {
  if (!window.confirm('确认删除这条留言？')) return
  try {
    await postApi.removeComment(comment.id)
    commentsMap[post.id] = (commentsMap[post.id] || []).filter((c) => c.id !== comment.id)
    post.comment_count = Math.max(0, post.comment_count - 1)
    post.heat = Math.max(0, post.heat - 1)
    notify('留言已删除')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除留言失败'
  }
}

function markImageFailed(postId: number, index: number) {
  failedImages[`${postId}-${index}`] = true
}

function changePage(next: number) {
  page.value = next
  load()
}

onMounted(() => {
  if (!auth.user) auth.fetchMe().catch(() => {})
  load()
})
</script>

<template>
  <div class="moments">
    <div v-if="error" class="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
      <button class="btn btn-quiet btn-sm" type="button" @click="error = ''">关闭</button>
    </div>
    <Transition name="fade">
      <div v-if="flash" class="toast">{{ flash }}</div>
    </Transition>

    <!-- QQ 空间风格顶部：背景图 + 头像在左、昵称与签名跟随其后 -->
    <section class="hero card">
      <div class="hero-cover" :style="coverStyle" :class="{ 'is-empty': !me?.cover }">
        <div class="hero-mask" />
        <button
          class="cover-btn"
          type="button"
          :disabled="uploadingCover"
          @click="coverInput?.click()"
        >
          <span v-if="uploadingCover" class="spinner" />
          <AppIcon v-else name="image" :size="14" />
          {{ uploadingCover ? '上传中…' : '更换背景' }}
        </button>
        <input
          ref="coverInput"
          type="file"
          accept="image/*"
          class="hidden-file"
          @change="onCoverChange"
        />
      </div>

      <div class="hero-body">
        <!-- 头像固定在左边，昵称 / 签名 / 统计依次跟随 -->
        <div class="hero-avatar">
          <img v-if="me?.avatar" :src="me.avatar" alt="头像" />
          <span v-else>{{ auth.avatarText }}</span>
        </div>

        <div class="hero-info">
          <h2 class="hero-name">{{ auth.displayName }}</h2>

          <!-- 个性备注：点击即可就地修改 -->
          <div class="bio-row">
            <template v-if="editingBio">
              <input
                ref="bioInput"
                v-model="bioDraft"
                class="bio-input"
                type="text"
                maxlength="80"
                placeholder="写一句个性备注，如：爱把行程排得刚刚好"
                @keydown.enter="saveBio"
                @keydown.esc="cancelBio"
                @blur="saveBio"
              />
              <button class="btn btn-primary btn-sm" type="button" @mousedown.prevent @click="saveBio">
                保存
              </button>
              <button class="btn btn-ghost btn-sm" type="button" @mousedown.prevent @click="cancelBio">
                取消
              </button>
            </template>
            <p
              v-else
              class="hero-bio"
              :class="{ 'is-empty': !me?.bio }"
              title="点击修改个性备注"
              @click="startBioEdit"
            >
              <span class="bio-text">{{ me?.bio || '点击这里写一句个性备注' }}</span>
              <AppIcon name="edit" :size="12" class="bio-pen" />
            </p>
          </div>

          <p class="hero-meta">
            <span class="meta-item"><AppIcon name="users" :size="13" />已关注 {{ followingCount }} 人</span>
            <span class="meta-dot">·</span>
            <span class="meta-item"><AppIcon name="check" :size="13" />好友 {{ friendsCount }} 人</span>
            <span class="meta-dot">·</span>
            <span class="meta-item"><AppIcon name="heart" :size="13" />粉丝 {{ followersCount }} 人</span>
            <span class="meta-dot">·</span>
            <span class="meta-item"><AppIcon name="activity" :size="13" />动态 {{ total }} 条</span>
          </p>
        </div>
        <button
          class="btn btn-primary btn-sm hero-publish"
          type="button"
          :disabled="isBanned"
          :title="isBanned ? '账号已被加入黑名单，暂时无法发布动态' : ''"
          @click="openCreate"
        >
          <AppIcon name="plus" :size="14" />
          发布动态
        </button>
      </div>

      <p v-if="isBanned" class="ban-notice">
        <AppIcon name="alert" :size="14" />
        你的账号已被管理员加入黑名单，暂时无法发布动态、点赞、评论与收藏。
      </p>
    </section>

    <div v-if="loading" class="list">
      <div v-for="i in 3" :key="i" class="card post-card skeleton-card">
        <div class="skeleton" style="height: 40px; width: 100%" />
        <div class="skeleton" style="height: 14px; width: 70%" />
        <div class="skeleton" style="height: 120px; width: 100%" />
      </div>
    </div>

    <EmptyState
      v-else-if="!moments.length"
      title="动态还是空的"
      description="去看看别人的旅行动态并关注他们，或先发布一条自己的动态吧。"
      action-text="去世界那么大看看"
      @action="router.push({ name: 'feed' })"
    />

    <div v-else class="list">
      <article v-for="post in moments" :key="post.id" class="card post-card">
        <header class="post-head">
          <div class="post-author">
            <div class="author-avatar">
              <img v-if="post.author.avatar" :src="post.author.avatar" alt="" />
              <span v-else>{{ (post.author.nickname || '旅').slice(0, 1) }}</span>
            </div>
            <div class="author-main">
              <div class="author-line">
                <span class="author-name">{{ post.author.nickname }}</span>
                <span v-if="isMine(post)" class="tag tag-me">我的动态</span>
                <span v-if="post.status !== 'published'" class="tag tag-draft">{{ post.status }}</span>
                <span
                  v-if="isMine(post) && post.visibility !== 'public'"
                  class="tag tag-vis"
                  :title="post.visibility === 'private' ? '仅自己可见' : '仅互关好友可见'"
                >{{ post.visibility === 'private' ? '仅自己可见' : '好友可见' }}</span>
              </div>
              <span class="post-time">{{ postTime(post) }}</span>
            </div>
          </div>
          <div class="post-head-right">
            <span class="heat" :title="'热度 = 点赞(每人一次) + 收藏 + 评论'">
              <AppIcon name="zap" :size="13" />
              {{ post.heat }}
            </span>
            <template v-if="isMine(post)">
              <button class="btn btn-ghost btn-sm" type="button" @click="openEdit(post)">
                <AppIcon name="edit" :size="13" /> 编辑
              </button>
              <button
                class="btn btn-danger btn-sm"
                type="button"
                :disabled="busyId === post.id"
                @click="removePost(post)"
              >
                <AppIcon name="trash" :size="13" /> 删除
              </button>
            </template>
          </div>
        </header>

        <h3 v-if="post.title" class="post-title">{{ post.title }}</h3>
        <p class="post-content">{{ post.content }}</p>

        <div v-if="post.images?.length" class="post-images" :class="`cols-${Math.min(post.images.length, 3)}`">
          <template v-for="(url, index) in post.images" :key="`${post.id}-${index}`">
            <img
              v-if="!failedImages[`${post.id}-${index}`]"
              class="post-image"
              :src="url"
              alt=""
              loading="lazy"
              @error="markImageFailed(post.id, index)"
            />
            <div v-else class="post-image is-broken">
              <AppIcon name="image" :size="16" />
            </div>
          </template>
        </div>

        <div v-if="post.tags?.length || post.city" class="post-tags">
          <span v-if="post.city" class="tag tag-city">
            <AppIcon name="map-pin" :size="12" />{{ post.city }}
          </span>
          <span v-for="tag in post.tags" :key="tag" class="tag">{{ tag }}</span>
        </div>

        <footer class="post-foot">
          <button class="foot-btn" :class="{ 'is-on': post.liked }" type="button" @click="toggleLike(post)">
            <AppIcon name="heart" :size="14" :fill="post.liked ? 'currentColor' : 'none'" />
            {{ post.like_count }}
          </button>
          <button class="foot-btn" :class="{ 'is-on': post.collected }" type="button" @click="toggleCollect(post)">
            <AppIcon name="star" :size="14" :fill="post.collected ? 'currentColor' : 'none'" />
            {{ post.collect_count }}
          </button>
          <button class="foot-btn" type="button" @click="toggleComments(post)">
            <AppIcon name="message" :size="14" />
            {{ post.comment_count }}
          </button>
          <button class="foot-btn" type="button" @click="router.push({ name: 'post-detail', params: { id: post.id } })">
            <AppIcon name="eye" :size="14" />
            {{ post.view_count }}
          </button>
        </footer>

        <div v-if="commentsOpen[post.id]" class="comments">
          <div v-if="commentLoading[post.id]" class="skeleton" style="height: 34px" />
          <template v-else>
            <p v-if="!commentsMap[post.id]?.length" class="muted comments-empty">还没有留言，来说两句吧。</p>
            <div v-for="c in commentsMap[post.id]" :key="c.id" class="comment">
              <div class="comment-avatar">
                <img v-if="c.author.avatar" :src="c.author.avatar" alt="" />
                <span v-else>{{ (c.author.nickname || '旅').slice(0, 1) }}</span>
              </div>
              <div class="comment-main">
                <div class="comment-head">
                  <span class="comment-name">{{ c.author.nickname }}</span>
                  <span v-if="editingCommentId !== c.id" class="comment-actions">
                    <button
                      v-if="c.user_id === me?.id"
                      class="link-btn"
                      type="button"
                      @click="startEditComment(c)"
                    >编辑</button>
                    <button
                      v-if="c.user_id === me?.id"
                      class="link-btn is-danger"
                      type="button"
                      @click="removeComment(post, c)"
                    >删除</button>
                  </span>
                </div>
                <template v-if="editingCommentId === c.id">
                  <div class="comment-edit">
                    <input v-model="editingCommentText" class="input" type="text" @keydown.enter="saveEditComment(post)" />
                    <button class="btn btn-primary btn-sm" type="button" @click="saveEditComment(post)">保存</button>
                    <button class="btn btn-ghost btn-sm" type="button" @click="editingCommentId = null">取消</button>
                  </div>
                </template>
                <p v-else class="comment-text">{{ c.content }}</p>
              </div>
            </div>

            <div class="comment-form">
              <input
                v-model="commentDraft[post.id]"
                class="input"
                type="text"
                placeholder="写下你的留言…（Enter 发送）"
                @keydown.enter="submitComment(post)"
              />
              <button class="btn btn-primary btn-sm" type="button" @click="submitComment(post)">
                <AppIcon name="send" :size="13" />
                发送
              </button>
            </div>
          </template>
        </div>
      </article>

      <div v-if="total > pageSize" class="pager">
        <button class="btn btn-ghost btn-sm" type="button" :disabled="page <= 1" @click="changePage(page - 1)">
          上一页
        </button>
        <span class="pager-text">第 {{ page }} / {{ Math.ceil(total / pageSize) }} 页</span>
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          :disabled="page >= Math.ceil(total / pageSize)"
          @click="changePage(page + 1)"
        >
          下一页
        </button>
      </div>
    </div>

    <PostFormDialog
      v-if="showForm"
      :post="editing"
      :saving="savingPost"
      @submit="submitPost"
      @close="showForm = false"
    />
  </div>
</template>

<style scoped>
.moments {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 860px;
  margin: 0 auto;
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

/* ---- 顶部背景 + 头像 ---- */
.hero {
  padding: 0;
  overflow: hidden;
}

.hero-cover {
  position: relative;
  /* 3:1 的封面比例（桌面约 820×273），比原先 4~5:1 的扁条更贴合常见风景照，
     大多数 4:3 / 3:2 / 16:9 的图都不会被裁得只剩一条 */
  aspect-ratio: 3 / 1;
  min-height: 200px;
  max-height: 300px;
  /* 默认底色 + 背景图铺满；主体偏上 30% 显示，避免裁掉画面重点 */
  background-color: #dbe4f8;
  background-image: var(--grad-primary);
  background-size: cover;
  background-repeat: no-repeat;
  background-position: center 30%;
}

.hero-cover.is-empty::after {
  content: '点击右上角「更换背景」上传你的主页背景图';
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  text-shadow: 0 1px 4px rgba(17, 24, 39, 0.35);
}

.hero-mask {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(17, 24, 39, 0.05) 0%, rgba(17, 24, 39, 0.42) 100%);
}

.cover-btn {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 9px;
  background: rgba(17, 24, 39, 0.42);
  color: #fff;
  font-size: 12.5px;
  backdrop-filter: blur(4px);
}

.cover-btn:hover:not(:disabled) {
  background: rgba(17, 24, 39, 0.62);
}

.hidden-file {
  display: none;
}

/* 头像作为左侧固定项，昵称/签名/统计在右侧跟随排列 */
.hero-avatar {
  position: relative;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 88px;
  height: 88px;
  flex-shrink: 0;
  margin-top: -52px;             /* 半压背景图下沿，但文字区不受影响 */
  border-radius: 26px;
  overflow: hidden;
  background: var(--grad-primary);
  border: 4px solid #fff;
  color: #fff;
  font-size: 28px;
  font-weight: 600;
  box-shadow: 0 8px 20px rgba(17, 24, 39, 0.2);
}

.hero-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hero-body {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  /* 顶部留 16px + 头像上移 52px：昵称起点在背景图之外，不会被背景图压住 */
  padding: 16px 22px 18px;
}

.hero-info {
  flex: 1;
  min-width: 220px;
  padding-top: 8px;
}

.ban-notice {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 22px 16px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.hero-name {
  font-size: 17px;
  font-weight: 650;
  line-height: 1.4;
}

/* 个性备注：整行可点，悬停显示铅笔提示 */
.bio-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  margin-top: 4px;
}

.hero-bio {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 2px 8px;
  margin-left: -8px;
  border-radius: 8px;
  font-size: 12.5px;
  color: var(--text-muted);
  cursor: pointer;
}

.hero-bio:hover {
  background: var(--panel-soft);
  color: var(--text);
}

.hero-bio.is-empty .bio-text {
  color: var(--text-faint);
}

.bio-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bio-pen {
  flex-shrink: 0;
  opacity: 0;
  color: var(--text-faint);
}

.hero-bio:hover .bio-pen {
  opacity: 1;
}

.bio-input {
  flex: 1;
  min-width: 160px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--primary);
  border-radius: 8px;
  background: #fff;
  font-size: 12.5px;
  outline: none;
}

.hero-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--text-faint);
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.meta-dot {
  color: var(--border);
}

.hero-publish {
  flex-shrink: 0;
}

/* ---- 动态列表 ---- */
.list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.post-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
}

.skeleton-card {
  pointer-events: none;
  gap: 10px;
}

.post-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.post-author {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.author-avatar {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 12px;
  overflow: hidden;
  background: var(--grad-primary);
  color: #fff;
  font-weight: 600;
}

.author-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.author-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.author-line {
  display: flex;
  align-items: center;
  gap: 7px;
}

.author-name {
  font-size: 13.5px;
  font-weight: 600;
}

.post-time {
  font-size: 11.5px;
  color: var(--text-faint);
}

.post-head-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.heat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 12px;
  font-weight: 600;
}

.post-title {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
}

.post-content {
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.post-images {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(3, 1fr);
  max-width: 480px;
}

.post-images.cols-1 {
  grid-template-columns: minmax(0, 320px);
}

.post-images.cols-2 {
  grid-template-columns: repeat(2, 1fr);
}

.post-image {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  border-radius: 10px;
  background: var(--panel-soft);
}

.post-image.is-broken {
  display: grid;
  place-items: center;
  color: var(--text-faint);
  border: 1px dashed var(--border);
}

.post-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 999px;
  background: #f3f4f6;
  color: var(--text-muted);
  font-size: 11.5px;
}

.tag-city {
  background: var(--primary-soft);
  color: var(--primary-strong);
}

.tag-me {
  background: var(--success-soft);
  color: var(--success);
}

.tag-draft {
  background: var(--warning-soft);
  color: var(--warning);
}

/* 可见范围标签：好友可见 / 仅自己可见 */
.tag-vis {
  background: #f1f4f9;
  color: var(--text-muted);
  border: 1px solid #dfe5ee;
}

.post-foot {
  display: flex;
  gap: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--border-soft);
}

.foot-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12.5px;
}

.foot-btn:hover {
  background: #f5f6f8;
  color: var(--text);
}

.foot-btn.is-on {
  color: var(--primary-strong);
}

.comments {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: 10px;
  background: var(--panel-soft);
  border: 1px solid var(--border-soft);
}

.comments-empty {
  font-size: 12.5px;
}

.comment {
  display: flex;
  gap: 9px;
}

.comment-avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 9px;
  overflow: hidden;
  background: var(--grad-primary);
  color: #fff;
  font-size: 12px;
}

.comment-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.comment-main {
  flex: 1;
  min-width: 0;
}

.comment-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.comment-name {
  font-size: 12.5px;
  font-weight: 600;
}

.comment-actions {
  display: inline-flex;
  gap: 8px;
  margin-left: auto;
}

.link-btn {
  border: none;
  background: transparent;
  color: var(--text-faint);
  font-size: 11.5px;
}

.link-btn:hover {
  color: var(--primary-strong);
}

.link-btn.is-danger:hover {
  color: var(--danger);
}

.comment-text {
  margin-top: 2px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text);
  word-break: break-word;
}

.comment-edit {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

.comment-form {
  display: flex;
  gap: 8px;
  margin-top: 4px;
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

.muted {
  color: var(--text-muted);
}

@media (max-width: 700px) {
  .hero-cover {
    aspect-ratio: 2 / 1;
    min-height: 180px;
  }

  .hero-avatar {
    width: 72px;
    height: 72px;
    margin-top: -44px;
    border-radius: 22px;
    font-size: 24px;
  }

  /* 窄屏：头像仍在左，信息块宽度自适应；发布按钮换行到下一行 */
  .hero-body {
    gap: 12px;
    padding: 14px 16px 16px;
  }

  .hero-info {
    min-width: 160px;
    padding-top: 4px;
  }

  .hero-publish {
    align-self: flex-start;
  }
}
</style>
