<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = withDefaults(
  defineProps<{
    src?: string
    name?: string
    size?: number
    radius?: number
    /** 传入用户 id 时头像可点击，跳转到该用户的公开主页 */
    userId?: number
  }>(),
  { src: '', name: '', size: 34, radius: 0, userId: 0 },
)

const router = useRouter()

const GRADIENTS = [
  'linear-gradient(135deg,#6366f1,#3b82f6)',
  'linear-gradient(135deg,#0ea5e9,#22c55e)',
  'linear-gradient(135deg,#f59e0b,#ef4444)',
  'linear-gradient(135deg,#8b5cf6,#ec4899)',
  'linear-gradient(135deg,#14b8a6,#0ea5e9)',
  'linear-gradient(135deg,#f43f5e,#f97316)',
]

function hashIndex(text: string): number {
  let sum = 0
  for (let i = 0; i < text.length; i += 1) sum += text.charCodeAt(i)
  return sum % GRADIENTS.length
}

const hasImage = computed(() => {
  const value = (props.src || '').trim()
  return value.startsWith('http') || value.startsWith('data:') || value.startsWith('/')
})

const initial = computed(() => (props.name || '旅').trim().slice(0, 1).toUpperCase())

const clickable = computed(() => Number(props.userId) > 0)

const style = computed(() => {
  const radius = props.radius || Math.round(props.size * 0.32)
  return {
    width: `${props.size}px`,
    height: `${props.size}px`,
    borderRadius: `${radius}px`,
    fontSize: `${Math.round(props.size * 0.42)}px`,
    background: hasImage.value ? '#eef1f5' : GRADIENTS[hashIndex(props.name || '旅')],
  }
})

/** 跳转到该用户主页；阻止冒泡，避免触发所在卡片自身的点击 */
function openProfile(event: MouseEvent) {
  if (!clickable.value) return
  event.stopPropagation()
  router.push({ name: 'user-profile', params: { id: props.userId } })
}
</script>

<template>
  <span
    class="ua"
    :class="{ 'is-clickable': clickable }"
    :style="style"
    :role="clickable ? 'link' : undefined"
    :tabindex="clickable ? 0 : undefined"
    :title="clickable ? `查看 ${name || '该用户'} 的主页` : undefined"
    @click="openProfile"
  >
    <img v-if="hasImage" :src="src" :alt="name || '头像'" />
    <span v-else class="ua-initial">{{ initial }}</span>
  </span>
</template>

<style scoped>
.ua {
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  overflow: hidden;
  color: #fff;
  font-weight: 600;
  user-select: none;
}

.ua.is-clickable {
  cursor: pointer;
  transition: box-shadow 0.16s ease, transform 0.16s ease;
}

.ua.is-clickable:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 0 2px var(--primary-soft);
}

.ua img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.ua-initial {
  line-height: 1;
}
</style>
