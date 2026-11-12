<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import { toolLabel } from '@/utils/format'

const props = defineProps<{
  tool: string
  args?: Record<string, unknown>
  status: 'running' | 'done'
  summary?: string
  source?: 'mcp' | 'native' | string
}>()

const THEME: Record<string, { icon: string; tone: string; action: string }> = {
  get_weather: { icon: 'cloud', tone: 'blue', action: '正在查询' },
  search_poi: { icon: 'map-pin', tone: 'green', action: '正在检索' },
  estimate_budget: { icon: 'wallet', tone: 'amber', action: '正在估算' },
  plan_route: { icon: 'route', tone: 'violet', action: '正在规划' },
  geocode: { icon: 'map-pin', tone: 'green', action: '正在定位' },
  reverse_geocode: { icon: 'map-pin', tone: 'green', action: '正在定位' },
  search_knowledge: { icon: 'compass', tone: 'amber', action: '正在检索知识库' },
  notify_desktop: { icon: 'bell', tone: 'slate', action: '正在推送提醒' },
  set_reminder: { icon: 'bell', tone: 'slate', action: '正在设置提醒' },
}

const theme = computed(() => THEME[props.tool] ?? { icon: 'sparkle', tone: 'slate', action: '正在调用' })

const argText = computed(() => {
  if (!props.args) return ''
  const entries = Object.entries(props.args).filter(([, value]) => value !== null && value !== '')
  if (!entries.length) return ''
  return entries
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`)
    .join(' · ')
})

const title = computed(() => {
  const target = props.args?.city ? String(props.args.city) : ''
  return `${theme.value.action}${target ? target : ''}${toolLabel(props.tool)}…`
})
</script>

<template>
  <div class="tool-card" :class="[`tone-${theme.tone}`, { 'is-done': status === 'done' }]">
    <span class="tool-icon">
      <AppIcon :name="theme.icon" :size="15" />
    </span>
    <div class="tool-body">
      <div class="tool-title">
        <span>{{ status === 'done' ? toolLabel(tool) + '完成' : title }}</span>
        <span class="tool-badge">{{ tool }}</span>
        <span v-if="source === 'mcp'" class="tool-src" title="经 MCP 子进程调用">MCP</span>
      </div>
      <div v-if="argText" class="tool-args">{{ argText }}</div>
      <div v-if="status === 'done' && summary" class="tool-summary">
        <AppIcon name="check" :size="13" />
        <span>{{ summary }}</span>
      </div>
    </div>
    <span class="tool-state">
      <span v-if="status === 'running'" class="dot-pulse" />
      <AppIcon v-else name="check" :size="14" />
    </span>
  </div>
</template>

<style scoped>
.tool-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #fff;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.tool-icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  flex-shrink: 0;
}

.tool-body {
  flex: 1;
  min-width: 0;
}

.tool-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.tool-badge {
  font-size: 11px;
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  color: var(--text-faint);
  background: #f4f5f7;
  padding: 0 6px;
  border-radius: 999px;
}

.tool-src {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.4px;
  color: var(--primary-strong);
  background: var(--primary-soft);
  padding: 0 6px;
  border-radius: 999px;
}

.tool-args {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-summary {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 5px;
  font-size: 12px;
  color: var(--success);
}

.tool-state {
  display: grid;
  place-items: center;
  width: 16px;
  height: 20px;
  color: var(--success);
}

.dot-pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.1s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1.15);
  }
}

.tone-blue .tool-icon {
  background: #eff6ff;
  color: #3b82f6;
}

.tone-green .tool-icon {
  background: #ecfdf3;
  color: #16a34a;
}

.tone-amber .tool-icon {
  background: #fff7ed;
  color: #d97706;
}

.tone-violet .tool-icon {
  background: #f5f3ff;
  color: #7c3aed;
}

.tone-slate .tool-icon {
  background: #f3f4f6;
  color: #6b7280;
}

.tool-card.is-done {
  border-color: var(--border-soft);
  background: var(--panel-soft);
}
</style>
