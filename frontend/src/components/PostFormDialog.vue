<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import { ApiError } from '@/api/http'
import { mediaApi } from '@/api/media'
import type { PostDetail, PostPayload, PostVisibility } from '@/types'

const props = withDefaults(
  defineProps<{
    post?: PostDetail | null
    saving?: boolean
  }>(),
  { post: null, saving: false },
)

const emit = defineEmits<{
  (e: 'submit', payload: PostPayload): void
  (e: 'close'): void
}>()

const isEdit = computed(() => Boolean(props.post))

const title = ref(props.post?.title ?? '')
const content = ref(props.post?.content ?? '')
const city = ref(props.post?.city ?? '')
const location = ref(props.post?.location ?? '')
const tagsText = ref((props.post?.tags ?? []).join('，'))
const imagesText = ref((props.post?.images ?? []).join('\n'))
const visibility = ref<PostVisibility>(props.post?.visibility ?? 'public')
const error = ref('')
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const failed = ref<Record<number, boolean>>({})

/** 可见范围选项：与后端 public / friends / private 一一对应 */
const VIS_OPTIONS: { value: PostVisibility; label: string; hint: string; icon: string }[] = [
  { value: 'public', label: '全部可见', hint: '所有人都能在广场看到', icon: 'globe' },
  { value: 'friends', label: '好友可见', hint: '仅互相关注的好友可见', icon: 'users' },
  { value: 'private', label: '仅自己可见', hint: '只出现在自己的动态里', icon: 'user' },
]

const MAX_IMAGES = 6

const imageLines = computed(() =>
  imagesText.value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean),
)

function triggerUpload() {
  fileInput.value?.click()
}

async function onFiles(event: Event) {
  const el = event.target as HTMLInputElement
  const files = Array.from(el.files ?? [])
  el.value = ''
  if (!files.length) return
  error.value = ''
  uploading.value = true
  const urls = imageLines.value.slice()
  try {
    for (const file of files) {
      if (urls.length >= MAX_IMAGES) break
      const res = await mediaApi.upload(file, 'image')
      urls.push(res.url)
    }
    imagesText.value = urls.slice(0, MAX_IMAGES).join('\n')
    failed.value = {}
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '图片上传失败'
  } finally {
    uploading.value = false
  }
}

function removeImage(index: number) {
  const urls = imageLines.value.slice()
  urls.splice(index, 1)
  imagesText.value = urls.join('\n')
  failed.value = {}
}

function markFailed(index: number) {
  failed.value[index] = true
}

function buildPayload(): PostPayload | null {
  if (!title.value.trim()) {
    error.value = '请填写标题'
    return null
  }
  if (!content.value.trim()) {
    error.value = '请填写正文内容'
    return null
  }
  if (!city.value.trim()) {
    error.value = '请填写城市'
    return null
  }
  const tags = tagsText.value
    .split(/[,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean)
  return {
    title: title.value.trim(),
    content: content.value.trim(),
    city: city.value.trim(),
    location: location.value.trim(),
    images: imageLines.value.slice(0, MAX_IMAGES),
    tags,
    visibility: visibility.value,
  }
}

function submit() {
  error.value = ''
  const payload = buildPayload()
  if (!payload) return
  emit('submit', payload)
}
</script>

<template>
  <AppModal
    :title="isEdit ? '编辑动态' : '发布动态'"
    subtitle="分享你的旅行见闻，与更多旅行者交流"
    wide
    @close="emit('close')"
  >
    <div class="form">
      <label class="field">
        <span class="field-label">标题</span>
        <input v-model="title" class="input" type="text" maxlength="60" placeholder="给这条动态起个标题" />
      </label>

      <div class="row-2">
        <label class="field">
          <span class="field-label">城市</span>
          <input v-model="city" class="input" type="text" placeholder="如 成都" />
        </label>
        <label class="field">
          <span class="field-label">地点</span>
          <input v-model="location" class="input" type="text" placeholder="如 宽窄巷子" />
        </label>
      </div>

      <label class="field">
        <span class="field-label">正文</span>
        <textarea
          v-model="content"
          class="textarea"
          rows="5"
          placeholder="记录你的行程、感受与实用攻略…"
        />
      </label>

      <label class="field">
        <span class="field-label">标签</span>
        <input v-model="tagsText" class="input" type="text" placeholder="用逗号分隔，如 美食，亲子，三日游" />
      </label>

      <div class="field">
        <span class="field-label">谁可以看</span>
        <div class="vis-options">
          <button
            v-for="opt in VIS_OPTIONS"
            :key="opt.value"
            class="vis-option"
            :class="{ 'is-active': visibility === opt.value }"
            type="button"
            @click="visibility = opt.value"
          >
            <AppIcon :name="opt.icon" :size="15" />
            <span class="vis-label">{{ opt.label }}</span>
            <span class="vis-hint">{{ opt.hint }}</span>
            <AppIcon v-if="visibility === opt.value" name="check" :size="13" class="vis-check" />
          </button>
        </div>
      </div>

      <div class="field">
        <div class="field-head">
          <span class="field-label">
            图片
            <span class="label-hint">可上传本地图片或粘贴 URL，最多 {{ MAX_IMAGES }} 张</span>
          </span>
          <button class="btn btn-ghost btn-sm" type="button" :disabled="uploading" @click="triggerUpload">
            <span v-if="uploading" class="spinner spinner-dark" />
            <AppIcon v-else name="upload" :size="14" />
            {{ uploading ? '上传中…' : '上传图片' }}
          </button>
          <input ref="fileInput" type="file" accept="image/*" multiple class="hidden-file" @change="onFiles" />
        </div>

        <div v-if="imageLines.length" class="thumb-grid">
          <div v-for="(url, index) in imageLines" :key="index" class="thumb">
            <img v-if="!failed[index]" :src="url" :alt="`图片 ${index + 1}`" @error="markFailed(index)" />
            <div v-else class="thumb-fallback">
              <AppIcon name="image" :size="16" />
            </div>
            <button class="thumb-del" type="button" title="移除这张图片" @click="removeImage(index)">
              <AppIcon name="close" :size="12" />
            </button>
          </div>
        </div>

        <textarea
          v-model="imagesText"
          class="textarea images-input"
          rows="2"
          placeholder="也可在此粘贴图片 URL，每行一个"
        />
      </div>

      <div v-if="error" class="form-error">
        <AppIcon name="alert" :size="14" />
        <span>{{ error }}</span>
      </div>
    </div>

    <template #footer>
      <button class="btn btn-ghost" type="button" @click="emit('close')">取消</button>
      <button class="btn btn-primary" type="button" :disabled="saving" @click="submit">
        <span v-if="saving" class="spinner" />
        {{ isEdit ? '保存修改' : '发布' }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.label-hint {
  margin-left: 6px;
  font-size: 11.5px;
  color: var(--text-faint);
  font-weight: 400;
}

/* 可见范围：三选一，选中项高亮描边 */
.vis-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.vis-option {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  color: var(--text-muted);
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.vis-option:hover {
  border-color: #c7d2e4;
}

.vis-option.is-active {
  border-color: var(--primary);
  background: #f4f8ff;
  color: var(--primary-strong);
}

.vis-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}

.vis-option.is-active .vis-label {
  color: var(--primary-strong);
}

.vis-hint {
  font-size: 11px;
  color: var(--text-faint);
  line-height: 1.4;
}

.vis-check {
  position: absolute;
  top: 8px;
  right: 8px;
  color: var(--primary);
}

.images-input {
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  font-size: 12.5px;
}

.field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.hidden-file {
  display: none;
}

.thumb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  gap: 8px;
}

.thumb {
  position: relative;
  aspect-ratio: 1 / 1;
  border-radius: 10px;
  overflow: hidden;
  background: #eef1f5;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.thumb-fallback {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  color: var(--text-faint);
  background: linear-gradient(135deg, #eef1f5, #e2e6ec);
}

.thumb-del {
  position: absolute;
  top: 4px;
  right: 4px;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: rgba(17, 24, 39, 0.6);
  color: #fff;
  transition: background 0.14s ease;
}

.thumb-del:hover {
  background: rgba(17, 24, 39, 0.85);
}

.form-error {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

@media (max-width: 560px) {
  .row-2 {
    grid-template-columns: 1fr;
  }
  .vis-options {
    grid-template-columns: 1fr;
  }
}
</style>
