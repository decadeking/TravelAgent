<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import UserAvatar from './UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const menuItems = [
  { label: '个人设置', icon: 'settings', hash: '' },
  { label: '偏好设置', icon: 'sliders', hash: '#preferences' },
  { label: '我的收藏', icon: 'star', hash: '#collections' },
  { label: 'Token 用量', icon: 'wallet', hash: '#usage' },
]

const name = computed(() => auth.displayName)
const avatar = computed(() => auth.user?.avatar || '')
const username = computed(() => (auth.user ? `@${auth.user.username}` : '未登录'))

function toggle() {
  open.value = !open.value
}

function go(hash: string) {
  open.value = false
  router.push({ name: 'profile', hash: hash || undefined })
}

function logout() {
  open.value = false
  auth.logout()
  router.replace({ name: 'login' })
}

function handleOutside(event: MouseEvent) {
  if (!open.value) return
  if (root.value && !root.value.contains(event.target as Node)) {
    open.value = false
  }
}

function handleKey(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('click', handleOutside)
  document.addEventListener('keydown', handleKey)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutside)
  document.removeEventListener('keydown', handleKey)
})
</script>

<template>
  <div ref="root" class="user-menu">
    <button
      class="avatar-btn"
      type="button"
      :aria-expanded="open"
      aria-haspopup="menu"
      title="账户菜单"
      @click="toggle"
    >
      <UserAvatar :src="avatar" :name="name" :size="30" :radius="15" />
      <span class="avatar-meta">
        <span class="avatar-name">{{ name }}</span>
        <span class="avatar-sub">{{ username }}</span>
      </span>
      <AppIcon name="chevron-down" :size="15" class="caret" :class="{ 'is-open': open }" />
    </button>

    <Transition name="fade">
      <div v-if="open" class="dropdown" role="menu">
        <div class="dropdown-head">
          <UserAvatar :src="avatar" :name="name" :size="38" :radius="12" />
          <div class="dropdown-head-text">
            <strong>{{ name }}</strong>
            <span class="faint">{{ username }}</span>
          </div>
        </div>

        <div class="dropdown-sep" />

        <button
          v-for="item in menuItems"
          :key="item.label"
          class="dropdown-item"
          type="button"
          role="menuitem"
          @click="go(item.hash)"
        >
          <AppIcon :name="item.icon" :size="16" />
          <span>{{ item.label }}</span>
        </button>

        <div class="dropdown-sep" />

        <button class="dropdown-item is-danger" type="button" role="menuitem" @click="logout">
          <AppIcon name="logout" :size="16" />
          <span>退出登录</span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.user-menu {
  position: relative;
}

.avatar-btn {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 42px;
  padding: 0 10px 0 6px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  transition: background 0.16s ease, border-color 0.16s ease;
}

.avatar-btn:hover {
  background: #f4f5f7;
  border-color: var(--border);
}

.avatar {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--grad-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.35);
}

.avatar-lg {
  width: 38px;
  height: 38px;
  font-size: 15px;
}

.avatar-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.2;
}

.avatar-name {
  font-size: 13px;
  font-weight: 600;
}

.avatar-sub {
  font-size: 11px;
  color: var(--text-faint);
}

.caret {
  color: var(--text-faint);
  transition: transform 0.18s ease;
}

.caret.is-open {
  transform: rotate(180deg);
}

.dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 232px;
  padding: 6px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-pop);
  z-index: 60;
}

.dropdown-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
}

.dropdown-head-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
  min-width: 0;
}

.dropdown-head-text strong {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dropdown-head-text .faint {
  font-size: 11px;
}

.dropdown-sep {
  height: 1px;
  margin: 5px 6px;
  background: var(--border-soft);
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  text-align: left;
  transition: background 0.14s ease, color 0.14s ease;
}

.dropdown-item:hover {
  background: #f5f6f8;
}

.dropdown-item.is-danger {
  color: var(--danger);
}

.dropdown-item.is-danger:hover {
  background: var(--danger-soft);
}

@media (max-width: 640px) {
  .avatar-meta,
  .caret {
    display: none;
  }

  .avatar-btn {
    padding: 0 6px;
  }
}
</style>
