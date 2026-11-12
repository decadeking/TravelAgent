<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusTag from '@/components/StatusTag.vue'
import { ApiError } from '@/api/http'
import { tripApi } from '@/api/trips'
import { categoryLabel, durationText, formatDateTime, formatMoney, timeSlotLabel } from '@/utils/format'
import type { TripDetail, TripStatus } from '@/types'

const route = useRoute()
const router = useRouter()

const trip = ref<TripDetail | null>(null)
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const message = ref('')

const statusOptions: Array<{ value: TripStatus; label: string }> = [
  { value: 'draft', label: '草稿' },
  { value: 'confirmed', label: '已确认' },
  { value: 'shared', label: '已分享' },
]

const tripId = computed(() => Number(route.params.id))

const remaining = computed(() => {
  if (!trip.value) return 0
  return Math.round((trip.value.budget - trip.value.total_cost) * 10) / 10
})

const overBudget = computed(() => remaining.value < 0)

const categoryRows = computed(() => {
  if (!trip.value) return []
  const map = new Map<string, number>()
  trip.value.day_list.forEach((day) =>
    day.items.forEach((item) => {
      map.set(item.category, (map.get(item.category) ?? 0) + item.cost)
    }),
  )
  return Array.from(map.entries())
    .map(([key, value]) => ({ key, label: categoryLabel(key), value: Math.round(value * 10) / 10 }))
    .sort((a, b) => b.value - a.value)
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    trip.value = await tripApi.detail(tripId.value)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载行程详情失败'
  } finally {
    loading.value = false
  }
}

async function changeStatus(status: TripStatus) {
  if (!trip.value || status === trip.value.status) return
  saving.value = true
  message.value = ''
  try {
    trip.value = await tripApi.update(trip.value.id, { status, version: trip.value.version })
    message.value = '行程状态已更新'
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '更新失败'
  } finally {
    saving.value = false
  }
}

async function removeTrip() {
  if (!trip.value) return
  if (!window.confirm(`确认删除行程「${trip.value.title}」？该操作不可撤销。`)) return
  try {
    await tripApi.remove(trip.value.id)
    router.replace({ name: 'trips' })
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <div class="detail">
    <button class="btn btn-quiet btn-sm back" type="button" @click="router.push({ name: 'trips' })">
      <AppIcon name="arrow-left" :size="15" />
      返回行程列表
    </button>

    <div v-if="loading" class="card loading-card">
      <div class="skeleton" style="height: 24px; width: 40%" />
      <div class="skeleton" style="height: 14px; width: 60%" />
      <div class="skeleton" style="height: 120px; width: 100%" />
      <div class="skeleton" style="height: 120px; width: 100%" />
    </div>

    <div v-else-if="error && !trip" class="card error-card">
      <AppIcon name="alert" :size="20" />
      <p>{{ error }}</p>
      <button class="btn btn-ghost btn-sm" type="button" @click="load">重试</button>
    </div>

    <EmptyState
      v-else-if="!trip"
      title="行程不存在"
      description="该行程可能已被删除，返回列表查看其他方案。"
      action-text="返回列表"
      @action="router.push({ name: 'trips' })"
    />

    <template v-else>
      <header class="card head-card">
        <div class="head-main">
          <div class="head-title-row">
            <h2>{{ trip.title }}</h2>
            <StatusTag :status="trip.status" />
          </div>
          <div class="head-meta">
            <span><AppIcon name="map-pin" :size="14" /> {{ trip.destination }}</span>
            <span class="meta-sep">·</span>
            <span><AppIcon name="calendar" :size="14" /> {{ trip.days }} 天</span>
            <span class="meta-sep">·</span>
            <span><AppIcon name="clock" :size="14" /> 更新于 {{ formatDateTime(trip.updated_at) }}</span>
            <span class="meta-sep">·</span>
            <span class="version">v{{ trip.version }}</span>
          </div>
        </div>

        <div class="head-actions">
          <label class="status-select">
            <span class="field-label">编辑状态</span>
            <select
              class="select"
              :value="trip.status"
              :disabled="saving"
              @change="changeStatus(($event.target as HTMLSelectElement).value as TripStatus)"
            >
              <option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </label>
          <button class="btn btn-danger btn-sm" type="button" @click="removeTrip">
            <AppIcon name="trash" :size="14" />
            删除
          </button>
        </div>
      </header>

      <div v-if="message" class="flash">
        <AppIcon name="check" :size="14" />
        {{ message }}
      </div>
      <div v-if="error" class="flash is-error">
        <AppIcon name="alert" :size="14" />
        {{ error }}
      </div>

      <div v-if="trip.remark" class="card remark-card">
        <span class="remark-title">旅程备注</span>
        <p class="remark-text">{{ trip.remark }}</p>
      </div>

      <div class="overview">
        <div class="card overview-card">
          <div class="overview-top">
            <span class="overview-label">预计总花费</span>
            <span class="overview-value" :class="{ 'is-over': overBudget }">{{ formatMoney(trip.total_cost) }}</span>
          </div>
          <div class="overview-bar">
            <div
              class="overview-fill"
              :class="{ 'is-over': overBudget }"
              :style="{ width: `${Math.min(100, trip.budget ? (trip.total_cost / trip.budget) * 100 : 0)}%` }"
            />
          </div>
          <div class="overview-foot">
            <span>预算 {{ formatMoney(trip.budget) }}</span>
            <span :class="overBudget ? 'over-text' : 'ok-text'">
              {{ overBudget ? `超出 ${formatMoney(Math.abs(remaining))}` : `剩余 ${formatMoney(remaining)}` }}
            </span>
          </div>
        </div>

        <div class="card overview-card">
          <span class="overview-label">费用构成</span>
          <ul class="cat-list">
            <li v-for="row in categoryRows" :key="row.key">
              <span class="tag tag-soft">{{ row.label }}</span>
              <span class="cat-value">{{ formatMoney(row.value) }}</span>
            </li>
            <li v-if="!categoryRows.length" class="faint">暂无费用明细</li>
          </ul>
        </div>
      </div>

      <section class="days">
        <article v-for="day in trip.day_list" :key="day.day_no" class="card day-card">
          <header class="day-head">
            <span class="day-badge">Day {{ day.day_no }}</span>
            <span class="day-city">{{ day.city }}</span>
            <span v-if="day.weather_snapshot" class="day-weather">
              <AppIcon name="cloud" :size="14" />
              {{ day.weather_snapshot }}
            </span>
          </header>
          <ul class="items">
            <li v-for="item in day.items" :key="item.seq" class="item">
              <span class="item-slot">{{ timeSlotLabel(item.time_slot) }}</span>
              <div class="item-body">
                <div class="item-name">{{ item.poi_name }}</div>
                <div class="item-meta">
                  <span class="tag tag-soft">{{ categoryLabel(item.category) }}</span>
                  <span class="meta-sep">·</span>
                  <span>{{ durationText(item.duration_min) }}</span>
                  <span class="meta-sep">·</span>
                  <span>{{ formatMoney(item.cost) }}</span>
                </div>
                <p v-if="item.note" class="item-note">{{ item.note }}</p>
              </div>
            </li>
            <li v-if="!day.items.length" class="faint item-empty">当天暂无安排</li>
          </ul>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 960px;
  margin: 0 auto;
}

.back {
  align-self: flex-start;
}

.loading-card,
.error-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 24px;
}

.error-card {
  align-items: center;
  color: var(--danger);
  text-align: center;
}

.head-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 20px;
  flex-wrap: wrap;
}

.head-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.head-title-row h2 {
  font-size: 20px;
  font-weight: 650;
}

.head-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.head-meta span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.meta-sep {
  color: var(--text-faint);
}

.version {
  padding: 1px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: var(--text-muted);
  font-size: 11.5px;
}

.head-actions {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}

.status-select {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.status-select .select {
  width: 132px;
  height: 34px;
}

.flash {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--success-soft);
  color: var(--success);
  font-size: 12.5px;
}

.flash.is-error {
  background: var(--danger-soft);
  color: var(--danger);
}

.remark-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 18px;
}

.remark-title {
  font-size: 12.5px;
  color: var(--text-muted);
}

.remark-text {
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--text);
  white-space: pre-wrap;
}

.overview {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
}

.overview-card {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.overview-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.overview-label {
  font-size: 12.5px;
  color: var(--text-muted);
}

.overview-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary-strong);
}

.overview-value.is-over {
  color: var(--danger);
}

.overview-bar {
  height: 8px;
  border-radius: 999px;
  background: #eef1f5;
  overflow: hidden;
}

.overview-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--grad-primary);
  transition: width 0.4s ease;
}

.overview-fill.is-over {
  background: linear-gradient(135deg, #f87171, #dc2626);
}

.overview-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12.5px;
  color: var(--text-muted);
}

.ok-text {
  color: var(--success);
}

.over-text {
  color: var(--danger);
  font-weight: 500;
}

.cat-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.cat-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
}

.cat-value {
  font-weight: 600;
}

.days {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.day-card {
  padding: 18px;
}

.day-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--border);
}

.day-badge {
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--grad-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.day-city {
  font-size: 14px;
  font-weight: 600;
}

.day-weather {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  font-size: 12.5px;
  color: var(--text-muted);
}

.items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 10px;
}

.item {
  display: flex;
  gap: 14px;
  padding: 11px 10px;
  border-radius: 10px;
  transition: background 0.15s ease;
}

.item:hover {
  background: var(--panel-soft);
}

.item-slot {
  width: 42px;
  flex-shrink: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--primary-strong);
}

.item-name {
  font-size: 14px;
  font-weight: 500;
}

.item-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 5px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.item-note {
  margin-top: 5px;
  font-size: 12.5px;
  color: var(--text-faint);
  line-height: 1.65;
}

.item-empty {
  padding: 10px;
  font-size: 12.5px;
}

@media (max-width: 720px) {
  .overview {
    grid-template-columns: 1fr;
  }

  .head-card {
    flex-direction: column;
  }
}
</style>
