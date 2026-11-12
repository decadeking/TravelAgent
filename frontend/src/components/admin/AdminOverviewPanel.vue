<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/http'
import type { AdminOverview, AdminStats } from '@/types'

const stats = ref<AdminStats | null>(null)
const overview = ref<AdminOverview | null>(null)
const loading = ref(true)
const error = ref('')
const flash = ref('')

const modelDown = ref(false)
const faultBusy = ref(false)

const STAT_LABELS: Record<string, string> = {
  users: '用户',
  posts: '动态',
  trips: '行程',
  sessions: '会话',
  comments: '留言',
  collections: '收藏',
  kb_documents: '知识文档',
  kb_chunks: '向量分块',
}

const statEntries = computed(() => {
  if (!stats.value) return []
  return Object.entries(stats.value)
    .filter(([, value]) => typeof value === 'number')
    .map(([key, value]) => ({ key, label: STAT_LABELS[key] ?? key, value: value as number }))
})

const counterEntries = computed(() => Object.entries(overview.value?.counters ?? {}))
const gaugeEntries = computed(() => Object.entries(overview.value?.gauges ?? {}))
const breakerEntries = computed(() => Object.entries(overview.value?.breakers ?? {}))

function breakerText(value: unknown): string {
  if (typeof value === 'object' && value !== null) {
    const record = value as Record<string, unknown>
    if ('state' in record) return String(record.state)
    return JSON.stringify(value)
  }
  return String(value)
}

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
    const [statsRes, overviewRes, faultRes] = await Promise.all([
      adminApi.stats(),
      adminApi.overview(),
      adminApi.getFault().catch(() => ({ model_down: false })),
    ])
    stats.value = statsRes
    overview.value = overviewRes
    modelDown.value = Boolean(faultRes?.model_down)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载概览失败'
  } finally {
    loading.value = false
  }
}

async function toggleFault() {
  faultBusy.value = true
  error.value = ''
  const next = !modelDown.value
  try {
    const res = await adminApi.setFault({ model_down: next })
    modelDown.value = Boolean(res?.model_down ?? next)
    notify(next ? '已开启模型故障演练' : '已关闭故障演练')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败'
  } finally {
    faultBusy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="panel">
    <div v-if="error" class="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
    </div>
    <div v-if="flash" class="alert is-ok">
      <AppIcon name="check" :size="14" />
      <span>{{ flash }}</span>
    </div>

    <div v-if="loading" class="rows">
      <div class="skeleton" style="height: 96px" />
      <div class="skeleton" style="height: 140px" />
    </div>

    <template v-else>
      <section class="stat-grid">
        <div v-for="item in statEntries" :key="item.key" class="stat-card card">
          <span class="stat-label">{{ item.label }}</span>
          <span class="stat-value">{{ item.value.toLocaleString('zh-CN') }}</span>
        </div>
      </section>

      <section class="metric-grid">
        <div class="card metric">
          <span class="metric-label"><AppIcon name="clock" :size="14" /> P95 延迟</span>
          <span class="metric-value">{{ overview?.p95_ms ?? 0 }} <em>ms</em></span>
        </div>
        <div class="card metric">
          <span class="metric-label"><AppIcon name="activity" :size="14" /> 近 1 小时 tokens</span>
          <span class="metric-value">{{ (overview?.tokens_last_hour ?? 0).toLocaleString('zh-CN') }}</span>
        </div>
        <div class="card metric">
          <span class="metric-label"><AppIcon name="globe" :size="14" /> SSE 连接数</span>
          <span class="metric-value">{{ overview?.sse_connections ?? 0 }}</span>
        </div>
      </section>

      <div class="two-col">
        <section class="card block">
          <header class="block-head">
            <h4><AppIcon name="activity" :size="15" /> 计数器</h4>
          </header>
          <ul class="kv">
            <li v-for="[key, value] in counterEntries" :key="key">
              <span class="kv-key">{{ key }}</span>
              <span class="kv-val">{{ value }}</span>
            </li>
            <li v-if="!counterEntries.length" class="empty-tip">暂无数据</li>
          </ul>
        </section>

        <section class="card block">
          <header class="block-head">
            <h4><AppIcon name="sliders" :size="15" /> 仪表盘</h4>
          </header>
          <ul class="kv">
            <li v-for="[key, value] in gaugeEntries" :key="key">
              <span class="kv-key">{{ key }}</span>
              <span class="kv-val">{{ value }}</span>
            </li>
            <li v-if="!gaugeEntries.length" class="empty-tip">暂无数据</li>
          </ul>
        </section>
      </div>

      <section class="card block">
        <header class="block-head">
          <div>
            <h4><AppIcon name="shield" :size="15" /> 熔断器状态</h4>
          </div>
        </header>
        <div class="breakers">
          <span v-for="[key, value] in breakerEntries" :key="key" class="breaker">
            <span class="breaker-name">{{ key }}</span>
            <span class="breaker-state">{{ breakerText(value) }}</span>
          </span>
          <span v-if="!breakerEntries.length" class="empty-tip">暂无熔断器</span>
        </div>
      </section>

      <section class="card block fault">
        <div class="fault-text">
          <h4><AppIcon name="zap" :size="15" /> 故障演练</h4>
          <p>开启后模拟模型不可用，用于验证降级与熔断逻辑。</p>
        </div>
        <button class="switch" :class="{ 'is-on': modelDown }" type="button" :disabled="faultBusy" @click="toggleFault" />
      </section>
    </template>
  </div>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.alert {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 13px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.alert.is-ok {
  background: var(--success-soft);
  color: var(--success);
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px;
}

.stat-label {
  font-size: 12.5px;
  color: var(--text-muted);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
}

.metric-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
}

.metric-value em {
  font-style: normal;
  font-size: 12.5px;
  color: var(--text-muted);
  font-weight: 500;
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.block {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.block-head h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 650;
}

.kv {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kv li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.kv-key {
  color: var(--text-muted);
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
}

.kv-val {
  font-weight: 600;
}

.breakers {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.breaker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--panel-soft);
  border: 1px solid var(--border-soft);
  font-size: 12px;
}

.breaker-name {
  color: var(--text-muted);
}

.breaker-state {
  font-weight: 600;
}

.fault {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.fault-text h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 650;
}

.fault-text p {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.empty-tip {
  padding: 16px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-faint);
}

@media (max-width: 780px) {
  .metric-grid {
    grid-template-columns: 1fr;
  }

  .two-col {
    grid-template-columns: 1fr;
  }
}
</style>
