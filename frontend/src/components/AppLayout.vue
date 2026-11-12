<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './Sidebar.vue'
import UserMenu from './UserMenu.vue'
import NotificationBell from './NotificationBell.vue'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const ui = useUiStore()
const pageTitle = computed(() => (route.meta.title as string) || '旅行吧')
const flush = computed(() => route.name === 'plan')
const collapsed = computed(() => ui.sidebarCollapsed)
</script>

<template>
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <Sidebar />
    <div class="app-main">
      <header class="topbar">
        <div class="topbar-title">
          <h1>{{ pageTitle }}</h1>
          <span class="topbar-sub">智能体驱动的旅行规划工作台</span>
        </div>
        <div class="topbar-right">
          <NotificationBell />
          <UserMenu />
        </div>
      </header>
      <main class="app-content" :class="{ 'is-flush': flush }">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--bg);
}

.app-main {
  margin-left: var(--sidebar-w);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  transition: margin-left 0.2s ease;
}

.app-shell.is-collapsed .app-main {
  margin-left: var(--sidebar-w-collapsed);
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 64px;
  padding: 0 24px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: saturate(180%) blur(10px);
  border-bottom: 1px solid var(--border);
}

.topbar-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}

.topbar-title h1 {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.topbar-sub {
  font-size: 12px;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-content {
  flex: 1;
  padding: 24px;
  min-width: 0;
}

.app-content.is-flush {
  padding: 0;
  overflow: hidden;
}

@media (max-width: 900px) {
  .app-main,
  .app-shell.is-collapsed .app-main {
    margin-left: 0;
  }

  .topbar {
    height: 58px;
    padding: 0 16px;
  }

  .topbar-sub {
    display: none;
  }

  .app-content {
    padding: 16px;
  }

  .app-content.is-flush {
    padding: 0;
  }
}
</style>
