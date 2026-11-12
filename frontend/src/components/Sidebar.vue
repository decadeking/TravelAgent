<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AppIcon from './AppIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useMessagesStore } from '@/stores/messages'
import { useUiStore } from '@/stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const messages = useMessagesStore()

const collapsed = computed(() => ui.sidebarCollapsed)

interface NavItem {
  name: string
  label: string
  icon: string
  to: string
  adminOnly?: boolean
}

const navItems: NavItem[] = [
  { name: 'feed', label: '世界那么大', icon: 'home', to: '/feed' },
  { name: 'plan', label: '新建规划', icon: 'compass', to: '/plan' },
  { name: 'trips', label: '个人行程', icon: 'calendar', to: '/trips' },
  { name: 'moments', label: '动态', icon: 'activity', to: '/moments' },
  { name: 'messages', label: '消息', icon: 'message', to: '/messages' },
  { name: 'admin', label: '管理', icon: 'shield', to: '/admin', adminOnly: true },
]

const visibleItems = computed(() => navItems.filter((item) => !item.adminOnly || auth.isAdmin))

// 有登录态时启动消息轮询（含未读徽标），登出即停止
watch(
  () => auth.user,
  (u) => {
    if (u) messages.startPolling()
    else messages.reset()
  },
  { immediate: true },
)

onMounted(() => {
  if (auth.user) messages.startPolling()
})

onBeforeUnmount(() => {
  /* 组件销毁不停止轮询：布局常驻，避免切页重复建定时器 */
})
</script>

<template>
  <aside class="sidebar" :class="{ 'is-collapsed': collapsed }">
    <div class="side-top">
      <RouterLink to="/feed" class="brand" title="旅行吧 TravelAgent">
        <span class="brand-mark">
          <!-- 白色风格 Logo：定位图钉 + 环绕轨道（呼应原深蓝图标，改为纯白以贴合网站浅色基调） -->
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" aria-hidden="true">
            <ellipse
              cx="12" cy="13.2" rx="10.4" ry="3.6"
              transform="rotate(-18 12 13.2)"
              stroke="#fff" stroke-width="1.4" opacity="0.72"
            />
            <path
              fill="#fff" fill-rule="evenodd"
              d="M12 2.4c-3.7 0-6.6 2.9-6.6 6.6 0 4.6 6.6 12.2 6.6 12.2s6.6-7.6 6.6-12.2c0-3.7-2.9-6.6-6.6-6.6Zm0 3.5a3.1 3.1 0 1 0 0 6.2 3.1 3.1 0 0 0 0-6.2Z"
            />
          </svg>
        </span>
        <span class="brand-text">
          <span class="brand-name">旅行吧</span>
          <span class="brand-sub">TravelAgent</span>
        </span>
      </RouterLink>

      <button
        class="collapse-btn"
        type="button"
        :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="ui.toggleSidebar()"
      >
        <AppIcon :name="collapsed ? 'chevron-right' : 'chevron-left'" :size="16" />
      </button>
    </div>

    <nav class="nav">
      <RouterLink
        v-for="item in visibleItems"
        :key="item.name"
        :to="item.to"
        class="nav-item"
        :title="collapsed ? item.label : undefined"
        active-class="is-active"
      >
        <AppIcon :name="item.icon" :size="18" />
        <span class="nav-label">{{ item.label }}</span>
        <span
          v-if="item.name === 'messages' && messages.unread > 0"
          class="nav-badge"
        >{{ messages.unread > 99 ? '99+' : messages.unread }}</span>
      </RouterLink>
    </nav>

    <div class="sidebar-foot">
      <div class="hint-card">
        <AppIcon name="sparkle" :size="15" />
        <p>描述你的旅行想法，智能体将为你生成可编辑的行程方案。</p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--sidebar-w);
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 16px 14px;
  background: #fff;
  border-right: 1px solid var(--border);
  transition: width 0.2s ease;
  z-index: 30;
}

.sidebar.is-collapsed {
  width: var(--sidebar-w-collapsed);
  padding: 16px 12px;
}

.side-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  padding: 6px 6px;
  border-radius: var(--radius-sm);
  transition: background 0.15s ease;
}

.brand:hover {
  background: #f7f8fa;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
  background: var(--grad-primary);
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.32);
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  overflow: hidden;
  white-space: nowrap;
}

.brand-name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.brand-sub {
  font-size: 11px;
  color: var(--text-faint);
  letter-spacing: 0.6px;
}

.collapse-btn {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: var(--text-muted);
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.collapse-btn:hover {
  border-color: #c8d6f5;
  color: var(--primary-strong);
  background: var(--primary-soft);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 11px;
  height: 40px;
  padding: 0 12px;
  border-radius: 10px;
  color: var(--text-muted);
  font-weight: 500;
  white-space: nowrap;
  transition: background 0.16s ease, color 0.16s ease;
}

.nav-item:hover {
  background: #f5f6f8;
  color: var(--text);
}

.nav-item.is-active {
  background: var(--primary-soft);
  color: var(--primary-strong);
  font-weight: 600;
}

.nav-badge {
  margin-left: auto;
  display: inline-grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.sidebar.is-collapsed .nav-badge {
  position: absolute;
  top: 4px;
  right: 6px;
  margin-left: 0;
  min-width: 8px;
  height: 8px;
  padding: 0;
  font-size: 0;
}

.sidebar.is-collapsed .nav-item {
  position: relative;
  justify-content: center;
  padding: 0;
  gap: 0;
}

.sidebar.is-collapsed .brand-text,
.sidebar.is-collapsed .nav-label,
.sidebar.is-collapsed .hint-card p,
.sidebar.is-collapsed .brand {
  display: none;
}

.sidebar.is-collapsed .side-top {
  flex-direction: column;
  gap: 10px;
}

.sidebar.is-collapsed .brand-mark {
  width: 34px;
}

.sidebar-foot {
  margin-top: auto;
}

.hint-card {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-radius: var(--radius-sm);
  background: var(--panel-soft);
  border: 1px solid var(--border-soft);
  color: var(--text-muted);
}

.hint-card p {
  font-size: 12px;
  line-height: 1.6;
}

.sidebar.is-collapsed .hint-card {
  justify-content: center;
  padding: 10px;
}

@media (max-width: 900px) {
  .sidebar,
  .sidebar.is-collapsed {
    /* 窄屏改为「静态」顶部横条：不再 fixed 覆盖顶栏，保证右上角头像可点击 */
    position: static;
    width: 100%;
    height: auto;
    flex-direction: row;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }

  .brand-text,
  .sidebar-foot,
  .collapse-btn {
    display: none;
  }

  .side-top,
  .sidebar.is-collapsed .side-top {
    flex: 0 0 auto;
    flex-direction: row;
    gap: 10px;
  }

  .brand,
  .sidebar.is-collapsed .brand {
    display: flex;
    padding: 0;
    flex: 0 0 auto;
  }

  .nav {
    flex-direction: row;
    gap: 2px;
    margin-left: auto;
  }

  .nav-item,
  .sidebar.is-collapsed .nav-item {
    height: 36px;
    padding: 0 10px;
    justify-content: center;
  }

  .nav-badge {
    position: absolute;
    top: 2px;
    right: 2px;
    margin-left: 0;
    min-width: 8px;
    height: 8px;
    padding: 0;
    font-size: 0;
  }

  .nav-label {
    display: none;
  }
}
</style>
