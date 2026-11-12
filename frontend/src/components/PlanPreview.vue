<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import EmptyState from './EmptyState.vue'
import MapView from './MapView.vue'
import { categoryLabel, durationText, formatMoney, timeSlotLabel } from '@/utils/format'
import type { MapMarker, PlanDraft } from '@/types'

const props = defineProps<{
  plan: PlanDraft | null
  loading?: boolean
}>()

// 地图不可用时（无点位 / 瓦片加载失败）整块收起，不占地方
const mapAvailable = ref(true)

const BREAKDOWN_META: Array<{ key: 'ticket' | 'hotel' | 'meals' | 'transport'; label: string; icon: string }> = [
  { key: 'ticket', label: '门票', icon: 'bookmark' },
  { key: 'hotel', label: '住宿', icon: 'map-pin' },
  { key: 'meals', label: '餐饮', icon: 'wallet' },
  { key: 'transport', label: '交通', icon: 'route' },
]

const ratio = computed(() => {
  if (!props.plan || !props.plan.budget) return 0
  return Math.min(999, Math.round((props.plan.total_cost / props.plan.budget) * 100))
})

const barWidth = computed(() => `${Math.min(100, ratio.value)}%`)

const overBudget = computed(() => {
  if (!props.plan) return false
  return !props.plan.within_budget || (props.plan.over_budget ?? 0) > 0
})

const remaining = computed(() => {
  if (!props.plan) return 0
  return Math.round((props.plan.budget - props.plan.total_cost) * 10) / 10
})

const breakdownRows = computed(() => {
  if (!props.plan?.breakdown) return []
  return BREAKDOWN_META.map((meta) => ({
    ...meta,
    value: Number(props.plan?.breakdown?.[meta.key] ?? 0),
  })).filter((row) => row.value > 0)
})

const markers = computed<MapMarker[]>(() => {
  const result: MapMarker[] = []
  props.plan?.day_list?.forEach((day) => {
    day.items.forEach((item) => {
      if (typeof item.lat === 'number' && typeof item.lon === 'number') {
        result.push({
          lat: item.lat,
          lon: item.lon,
          label: item.poi_name,
          meta: `Day ${day.day_no} · ${day.city}`,
        })
      }
    })
  })
  return result
})

const center = computed(() => props.plan?.center ?? null)

// 目的地配图：地点配图偶发无法生成，失败时退化为「通用旅行风景」保底图，
// 若保底图也失败，则只剩纯色底 + 地名，不影响布局与可读性。
const GENERIC_DEST_IMAGE = `https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=${encodeURIComponent('旅行 风景 山水 城市 日落 通用配图 高清')}&image_size=landscape_16_9`
const destImageFailed = ref(false)

const destImage = computed(() => {
  const city = props.plan?.destination || ''
  if (!city) return ''
  if (destImageFailed.value) return GENERIC_DEST_IMAGE
  const prompt = encodeURIComponent(`${city} 城市风光 旅行 地标 摄影 高清`)
  return `https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=${prompt}&image_size=landscape_16_9`
})

function onDestImageError() {
  destImageFailed.value = true   // 地点图失败 → 切保底图；保底图再失败 img 直接隐藏
}

// 切换目的地时重置失败标记，避免上一张图的失败状态影响新目的地
watch(() => props.plan?.destination, () => { destImageFailed.value = false })
</script>

<template>
  <div class="preview">
    <template v-if="plan">
      <header class="preview-head">
        <div class="preview-head-top">
          <div>
            <h2 class="preview-title">{{ plan.title }}</h2>
            <p class="preview-sub">
              <AppIcon name="map-pin" :size="13" />
              <span>{{ plan.destination }}</span>
              <span class="dot">·</span>
              <span>{{ plan.days }} 天</span>
              <span v-if="plan.degraded" class="tag tag-draft">降级参考</span>
            </p>
          </div>
        </div>

        <!-- 预算非必填：用户填了预算才展示预算条 -->
        <div v-if="plan.budget > 0" class="budget" :class="{ 'is-over': overBudget }">
          <div class="budget-row">
            <span class="budget-label">预计总花费</span>
            <span class="budget-value">
              {{ formatMoney(plan.total_cost) }}
              <em>/ 预算 {{ formatMoney(plan.budget) }}</em>
            </span>
          </div>
          <div class="budget-track">
            <div class="budget-fill" :style="{ width: barWidth }" />
          </div>
          <div class="budget-foot">
            <span v-if="overBudget" class="over-text">
              <AppIcon name="alert" :size="13" />
              已超出预算约 {{ formatMoney(plan.over_budget || Math.abs(remaining)) }}
            </span>
            <span v-else class="ok-text">预算充足，剩余约 {{ formatMoney(remaining) }}</span>
            <span class="muted">{{ ratio }}%</span>
          </div>
        </div>

        <div v-if="breakdownRows.length" class="breakdown">
          <div v-for="row in breakdownRows" :key="row.key" class="breakdown-item">
            <AppIcon :name="row.icon" :size="13" />
            <span class="breakdown-label">{{ row.label }}</span>
            <span class="breakdown-value">{{ formatMoney(row.value) }}</span>
          </div>
        </div>
      </header>

      <!-- 目的地卡片：始终显示地名；地点图生成失败时自动切通用保底图 -->
      <section v-if="plan.destination" class="dest-card">
        <img
          v-if="destImage"
          class="dest-bg"
          :src="destImage"
          alt=""
          @error="onDestImageError"
        >
        <div class="dest-info">
          <span class="dest-name">
            <AppIcon name="map-pin" :size="15" />
            {{ plan.destination }}
          </span>
          <span class="dest-meta">
            {{ plan.days }} 天 · {{ markers.length }} 个坐标点位 · 智能体已检索周边景点、玩法与门票
          </span>
        </div>
      </section>

      <section v-if="mapAvailable" class="map-section">
        <h3 class="section-title">
          <AppIcon name="map-pin" :size="14" />
          行程地图
        </h3>
        <MapView :center="center" :markers="markers" :height="260" @available="mapAvailable = $event" />
      </section>

      <div v-if="plan.warnings?.length" class="warnings">
        <div v-for="(warn, i) in plan.warnings" :key="i" class="warning-item">
          <AppIcon name="alert" :size="13" />
          <span>{{ warn }}</span>
        </div>
      </div>

      <section class="days">
        <article v-for="day in plan.day_list" :key="day.day_no" class="day">
          <div class="day-head">
            <span class="day-badge">Day {{ day.day_no }}</span>
            <span class="day-city">{{ day.city }}</span>
            <span v-if="day.weather" class="day-weather">
              <AppIcon name="cloud" :size="13" />
              {{ day.weather }}
            </span>
            <span class="day-cost">{{ formatMoney(day.day_cost) }}</span>
          </div>

          <ul class="items">
            <li v-for="(item, index) in day.items" :key="index" class="item">
              <span class="item-slot">{{ timeSlotLabel(item.time_slot) }}</span>
              <div class="item-body">
                <div class="item-name">{{ item.poi_name }}</div>
                <div class="item-meta">
                  <span class="tag tag-soft">{{ categoryLabel(item.category) }}</span>
                  <span class="meta-dot">·</span>
                  <span>{{ durationText(item.duration_min) }}</span>
                  <span class="meta-dot">·</span>
                  <span>{{ formatMoney(item.cost) }}</span>
                </div>
                <p v-if="item.note" class="item-note">{{ item.note }}</p>
              </div>
            </li>
            <li v-if="!day.items.length" class="item-empty">当天暂无安排</li>
          </ul>
        </article>
      </section>

      <section v-if="plan.citations?.length" class="citations">
        <h3 class="section-title">
          <AppIcon name="file-text" :size="14" />
          RAG 引用来源
        </h3>
        <ul>
          <li v-for="cite in plan.citations" :key="cite.chunk_id" class="citation">
            <div class="citation-head">
              <span class="citation-title">{{ cite.title || cite.city || '知识片段' }}</span>
              <span class="citation-score">相关度 {{ (cite.score ?? 0).toFixed(2) }}</span>
            </div>
            <p class="citation-text">{{ cite.text }}</p>
          </li>
        </ul>
      </section>
    </template>

    <div v-else class="preview-empty">
      <EmptyState
        title="行程预览区"
        description="发送一条旅行需求，智能体生成的行程会实时呈现在这里：按天时间轴、预算明细与引用来源。"
      />
      <div v-if="loading" class="preview-skeleton">
        <div class="skeleton" style="height: 64px" />
        <div class="skeleton" style="height: 96px" />
        <div class="skeleton" style="height: 96px" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.preview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preview-head {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
}

.preview-title {
  font-size: 16px;
  font-weight: 600;
}

.preview-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.preview-sub .dot {
  color: var(--text-faint);
}

.preview-sub .tag {
  margin-left: 6px;
}

.budget {
  padding: 12px;
  border-radius: 10px;
  background: var(--primary-soft);
}

.budget.is-over {
  background: var(--danger-soft);
}

.budget-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.budget-label {
  font-size: 12.5px;
  color: var(--text-muted);
}

.budget-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--primary-strong);
}

.budget.is-over .budget-value {
  color: var(--danger);
}

.budget-value em {
  font-style: normal;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
}

.budget-track {
  height: 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.85);
  overflow: hidden;
}

.budget-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--grad-primary);
  transition: width 0.45s cubic-bezier(0.22, 1, 0.36, 1);
}

.budget.is-over .budget-fill {
  background: linear-gradient(135deg, #f87171, #dc2626);
}

.budget-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
}

.over-text {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--danger);
  font-weight: 500;
}

.ok-text {
  color: var(--success);
}

.breakdown {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
  gap: 8px;
}

.breakdown-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 9px;
  background: var(--panel-soft);
  border: 1px solid var(--border-soft);
  font-size: 12px;
  color: var(--text-muted);
}

.breakdown-label {
  flex: 1;
}

.breakdown-value {
  font-weight: 600;
  color: var(--text);
}

.warnings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.warning-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  border-radius: 9px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 12.5px;
}

.days {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.map-section {
  display: flex;
  flex-direction: column;
}

.dest-card {
  position: relative;
  min-height: 132px;
  display: flex;
  align-items: flex-end;
  padding: 14px;
  border-radius: var(--radius);
  overflow: hidden;
  background: linear-gradient(135deg, #334155 0%, #0f172a 100%);
  border: 1px solid var(--border);
}

/* 地点配图（失败即隐藏，露出下面的渐变底） */
.dest-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 0;
}

/* 压暗蒙层，保证地名在亮色照片上依然清晰 */
.dest-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.05) 20%, rgba(15, 23, 42, 0.72));
  z-index: 1;
}

.dest-info {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #fff;
}

.dest-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 17px;
  font-weight: 700;
  text-shadow: 0 1px 4px rgba(15, 23, 42, 0.6);
}

.dest-meta {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.88);
  text-shadow: 0 1px 3px rgba(15, 23, 42, 0.55);
}

.day {
  padding: 14px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
}

.day-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px dashed var(--border);
}

.day-badge {
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--grad-primary);
  color: #fff;
  font-size: 11.5px;
  font-weight: 600;
}

.day-city {
  font-size: 13.5px;
  font-weight: 600;
}

.day-weather {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.day-cost {
  margin-left: auto;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--primary-strong);
}

.items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 8px;
}

.item {
  display: flex;
  gap: 12px;
  padding: 10px 8px;
  border-radius: 9px;
  transition: background 0.15s ease;
}

.item:hover {
  background: var(--panel-soft);
}

.item-slot {
  width: 40px;
  flex-shrink: 0;
  padding-top: 1px;
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-strong);
}

.item-body {
  min-width: 0;
}

.item-name {
  font-size: 13.5px;
  font-weight: 500;
}

.item-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.meta-dot {
  color: var(--text-faint);
}

.item-note {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-faint);
  line-height: 1.6;
}

.item-empty {
  padding: 10px;
  font-size: 12.5px;
  color: var(--text-faint);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
}

.citations {
  padding: 14px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
}

.citation {
  padding: 10px 12px;
  border-left: 3px solid var(--primary);
  border-radius: 6px;
  background: var(--panel-soft);
}

.citation + .citation {
  margin-top: 8px;
}

.citation-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12.5px;
}

.citation-title {
  font-weight: 600;
}

.citation-score {
  color: var(--text-faint);
  font-size: 11.5px;
  white-space: nowrap;
}

.citation-text {
  margin-top: 5px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.65;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.preview-empty {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.preview-skeleton {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
