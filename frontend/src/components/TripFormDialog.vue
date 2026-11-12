<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import type { TripFormResult, TripStatus, TripSummary } from '@/types'

const props = withDefaults(
  defineProps<{
    trip?: TripSummary | null
    saving?: boolean
  }>(),
  { trip: null, saving: false },
)

const emit = defineEmits<{
  (e: 'submit', payload: TripFormResult): void
  (e: 'close'): void
}>()

const isEdit = computed(() => Boolean(props.trip))

const title = ref(props.trip?.title ?? '')
const destination = ref(props.trip?.destination ?? '')
const days = ref(String(props.trip?.days ?? 3))
const budget = ref(String(props.trip?.budget ?? 3000))
const status = ref<TripStatus>(props.trip?.status ?? 'draft')
const remark = ref(props.trip?.remark ?? '')
const startDate = ref(props.trip?.start_date ?? '')
const error = ref('')

const STATUS_OPTIONS: Array<{ value: TripStatus; label: string }> = [
  { value: 'draft', label: '草稿' },
  { value: 'confirmed', label: '已确认' },
  { value: 'shared', label: '已分享' },
]

function submit() {
  error.value = ''
  if (!title.value.trim()) {
    error.value = '请填写行程标题'
    return
  }
  if (!destination.value.trim()) {
    error.value = '请填写目的地'
    return
  }
  const dayNum = Number(days.value)
  if (!dayNum || dayNum < 1 || dayNum > 30) {
    error.value = '天数需在 1 - 30 之间'
    return
  }
  const budgetNum = Number(budget.value)
  if (Number.isNaN(budgetNum) || budgetNum < 0) {
    error.value = '请填写有效预算'
    return
  }
  emit('submit', {
    title: title.value.trim(),
    destination: destination.value.trim(),
    days: Math.round(dayNum),
    budget: Math.round(budgetNum),
    status: status.value,
    remark: remark.value.trim(),
    start_date: startDate.value,
  })
}
</script>

<template>
  <AppModal
    :title="isEdit ? '编辑行程' : '新建行程'"
    subtitle="填写基础信息，稍后可在详情页补充每日安排"
    @close="emit('close')"
  >
    <div class="form">
      <label class="field">
        <span class="field-label">行程标题</span>
        <input v-model="title" class="input" type="text" placeholder="如 成都亲子四日游" />
      </label>

      <label class="field">
        <span class="field-label">目的地</span>
        <input v-model="destination" class="input" type="text" placeholder="如 成都" />
      </label>

      <div class="row-2">
        <label class="field">
          <span class="field-label">天数</span>
          <input v-model="days" class="input" type="number" min="1" max="30" placeholder="3" />
        </label>
        <label class="field">
          <span class="field-label">预算（元）</span>
          <input v-model="budget" class="input" type="number" min="0" placeholder="3000" />
        </label>
      </div>

      <label class="field">
        <span class="field-label">出发日期</span>
        <input v-model="startDate" class="input" type="date" />
        <span class="field-hint">
          <AppIcon name="bell" :size="12" />
          确认日期后自动开启提醒：出发前一天站内提醒，出发当天桌面通知
        </span>
      </label>

      <label class="field">
        <span class="field-label">状态</span>
        <select v-model="status" class="select">
          <option v-for="opt in STATUS_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </label>

      <label class="field">
        <span class="field-label">旅程备注</span>
        <textarea
          v-model="remark"
          class="textarea"
          rows="3"
          maxlength="1000"
          placeholder="补充这次行程的说明，如出行偏好、同行人、注意事项…"
        />
      </label>

      <div v-if="error" class="form-error">
        <AppIcon name="alert" :size="14" />
        <span>{{ error }}</span>
      </div>
    </div>

    <template #footer>
      <button class="btn btn-ghost" type="button" @click="emit('close')">取消</button>
      <button class="btn btn-primary" type="button" :disabled="saving" @click="submit">
        <span v-if="saving" class="spinner" />
        {{ isEdit ? '保存修改' : '创建行程' }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.field-hint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 5px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-faint);
}

.form-error {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

@media (max-width: 520px) {
  .row-2 {
    grid-template-columns: 1fr;
  }
}
</style>
