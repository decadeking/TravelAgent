<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import AdminPostsPanel from '@/components/admin/AdminPostsPanel.vue'
import AdminSettingsPanel from '@/components/admin/AdminSettingsPanel.vue'
import AdminKbPanel from '@/components/admin/AdminKbPanel.vue'
import AdminOverviewPanel from '@/components/admin/AdminOverviewPanel.vue'
import AdminMediaPanel from '@/components/admin/AdminMediaPanel.vue'
import AdminBlacklistPanel from '@/components/admin/AdminBlacklistPanel.vue'

type TabKey = 'posts' | 'settings' | 'kb' | 'media' | 'blacklist' | 'overview'

const tabs: Array<{ key: TabKey; label: string; icon: string }> = [
  { key: 'posts', label: '内容审核', icon: 'shield' },
  { key: 'settings', label: '系统设置', icon: 'settings' },
  { key: 'kb', label: '知识库', icon: 'book' },
  { key: 'media', label: '图片资源', icon: 'image' },
  { key: 'blacklist', label: '黑名单', icon: 'user' },
  { key: 'overview', label: '概览', icon: 'activity' },
]

const active = ref<TabKey>('overview')

function select(key: TabKey) {
  active.value = key
}
</script>

<template>
  <div class="admin">
    <header class="page-head">
      <div>
        <h2 class="page-title">管理后台</h2>
        <p class="page-desc">内容审核、系统设置与知识库维护，仅管理员可见。</p>
      </div>
      <span class="role-badge">
        <AppIcon name="shield" :size="14" />
        管理员
      </span>
    </header>

    <div class="line-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="line-tab"
        :class="{ 'is-active': active === tab.key }"
        type="button"
        @click="select(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="tab-body">
      <AdminOverviewPanel v-if="active === 'overview'" />
      <AdminPostsPanel v-else-if="active === 'posts'" />
      <AdminSettingsPanel v-else-if="active === 'settings'" />
      <AdminKbPanel v-else-if="active === 'kb'" />
      <AdminMediaPanel v-else-if="active === 'media'" />
      <AdminBlacklistPanel v-else-if="active === 'blacklist'" />
    </div>
  </div>
</template>

<style scoped>
.admin {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 1100px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: 0.2px;
}

.page-desc {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-muted);
}

.role-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  background: var(--primary-soft);
  color: var(--primary-strong);
  font-size: 12.5px;
  font-weight: 500;
}

.tab-body {
  padding-top: 4px;
}
</style>
