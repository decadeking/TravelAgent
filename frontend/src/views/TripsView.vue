<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusTag from '@/components/StatusTag.vue'
import TripFormDialog from '@/components/TripFormDialog.vue'
import { ApiError } from '@/api/http'
import { tripApi } from '@/api/trips'
import { formatDateTime, formatMoney } from '@/utils/format'
import type { TripFormResult, TripStatus, TripSummary } from '@/types'

const router = useRouter()

const items = ref<TripSummary[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 9
const status = ref<TripStatus | ''>('')
const loading = ref(true)
const error = ref('')
const busyId = ref<number | null>(null)

const showForm = ref(false)
const editing = ref<TripSummary | null>(null)
const saving = ref(false)

const STATUS_OPTIONS: Array<{ value: TripStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'confirmed', label: '已确认' },
  { value: 'shared', label: '已分享' },
]

const totalPages = ref(1)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await tripApi.list({ page: page.value, page_size: pageSize, status: status.value })
    items.value = res.items
    total.value = res.total
    totalPages.value = Math.max(1, Math.ceil(res.total / res.page_size))
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载行程失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  showForm.value = true
}

function openEdit(trip: TripSummary) {
  editing.value = trip
  showForm.value = true
}

async function submitTrip(payload: TripFormResult) {
  saving.value = true
  error.value = ''
  try {
    if (editing.value) {
      const detail = await tripApi.detail(editing.value.id)
      await tripApi.update(editing.value.id, { ...payload, version: detail.version })
    } else {
      await tripApi.create({ ...payload, day_list: [] })
    }
    showForm.value = false
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function removeTrip(trip: TripSummary) {
  if (!window.confirm(`确认删除行程「${trip.title}」？该操作不可撤销。`)) return
  busyId.value = trip.id
  try {
    await tripApi.remove(trip.id)
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '删除失败'
  } finally {
    busyId.value = null
  }
}

function goDetail(id: number) {
  router.push({ name: 'trip-detail', params: { id } })
}

function changePage(next: number) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
}

watch(status, () => {
  page.value = 1
  load()
})

onMounted(load)
</script>

<template>
  <div class="trips">
    <header class="page-head">
      <!-- 左上角「个人行程」已由顶部标题栏统一展示，这里只保留放大的说明文字 -->
      <p class="page-desc">共 {{ total }} 份行程方案，随时查看、编辑与分享。</p>
      <div class="page-actions">
        <select v-model="status" class="select" style="width: 132px">
          <option v-for="opt in STATUS_OPTIONS" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <button class="btn btn-primary" type="button" @click="openCreate">
          <AppIcon name="plus" :size="16" />
          新建行程
        </button>
      </div>
    </header>

    <div v-if="error" class="alert">
      <AppIcon name="alert" :size="14" />
      <span>{{ error }}</span>
    </div>

    <div v-if="loading" class="grid">
      <div v-for="i in 6" :key="i" class="card trip-card skeleton-card">
        <div class="skeleton" style="height: 18px; width: 60%" />
        <div class="skeleton" style="height: 13px; width: 40%" />
        <div class="skeleton" style="height: 13px; width: 76%" />
        <div class="skeleton" style="height: 32px; width: 100%; margin-top: auto" />
      </div>
    </div>

    <EmptyState
      v-else-if="!items.length"
      title="还没有行程"
      description="从一个想法开始吧，告诉智能体你想去哪、玩几天、预算多少。"
      action-text="去规划"
      @action="router.push({ name: 'plan' })"
    />

    <template v-else>
      <div class="grid">
        <article v-for="trip in items" :key="trip.id" class="card trip-card">
          <div class="trip-top">
            <h3 class="trip-title" :title="trip.title">{{ trip.title }}</h3>
            <StatusTag :status="trip.status" />
          </div>

          <div class="trip-goal">
            <AppIcon name="map-pin" :size="14" />
            <span>{{ trip.destination }}</span>
          </div>

          <div class="trip-stats">
            <div class="stat">
              <span class="stat-label">天数</span>
              <span class="stat-value">{{ trip.days }} 天</span>
            </div>
            <div class="stat">
              <span class="stat-label">预算</span>
              <span class="stat-value">{{ formatMoney(trip.budget) }}</span>
            </div>
            <div class="stat">
              <span class="stat-label">{{ trip.start_date ? '出发' : '更新' }}</span>
              <span class="stat-value small">
                {{ trip.start_date || formatDateTime(trip.updated_at) }}
              </span>
            </div>
          </div>

          <p v-if="trip.start_date" class="trip-remind">
            <AppIcon name="bell" :size="13" />
            已开启出发提醒：出发前一天站内提醒，出发当天桌面通知
          </p>

          <p v-if="trip.remark" class="trip-remark" :title="trip.remark">{{ trip.remark }}</p>

          <div class="trip-foot">
            <button class="btn btn-ghost btn-sm" type="button" @click="goDetail(trip.id)">
              <AppIcon name="file-text" :size="14" />
              详情
            </button>
            <button class="btn btn-ghost btn-sm" type="button" @click="openEdit(trip)">
              <AppIcon name="edit" :size="14" />
              编辑
            </button>
            <button
              class="btn btn-danger btn-sm"
              type="button"
              :disabled="busyId === trip.id"
              @click="removeTrip(trip)"
            >
              <AppIcon name="trash" :size="14" />
              删除
            </button>
          </div>
        </article>
      </div>

      <div v-if="totalPages > 1" class="pager">
        <button class="btn btn-ghost btn-sm" type="button" :disabled="page <= 1" @click="changePage(page - 1)">
          上一页
        </button>
        <span class="pager-text">第 {{ page }} / {{ totalPages }} 页</span>
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          :disabled="page >= totalPages"
          @click="changePage(page + 1)"
        >
          下一页
        </button>
      </div>
    </template>

    <TripFormDialog
      v-if="showForm"
      :trip="editing"
      :saving="saving"
      @submit="submitTrip"
      @close="showForm = false"
    />
  </div>
</template>

<style scoped>
.trips {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1180px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

/* 说明文字改为页头主文案：字号放大、左对齐、加粗一档 */
.page-desc {
  flex: 1;
  min-width: 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--text);
  letter-spacing: 0.1px;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.alert {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 13px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.trip-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.trip-card:hover {
  border-color: #d8dee8;
  box-shadow: 0 4px 14px rgba(17, 24, 39, 0.07);
  transform: translateY(-1px);
}

.skeleton-card {
  pointer-events: none;
}

.trip-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.trip-title {
  font-size: 15.5px;
  font-weight: 600;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.trip-goal {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
}

.trip-remark {
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.trip-remind {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--success);
}

.trip-stats {
  display: flex;
  gap: 18px;
  padding: 12px;
  border-radius: 10px;
  background: var(--panel-soft);
  border: 1px solid var(--border-soft);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.stat-label {
  font-size: 11.5px;
  color: var(--text-faint);
}

.stat-value {
  font-size: 13.5px;
  font-weight: 600;
}

.stat-value.small {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
}

.trip-foot {
  display: flex;
  gap: 8px;
  margin-top: auto;
  padding-top: 4px;
}

.trip-foot .btn {
  flex: 1;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
}

.pager-text {
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
