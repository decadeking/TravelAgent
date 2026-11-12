// 通用格式化工具

export function formatMoney(value: number | null | undefined): string {
  const num = Number(value ?? 0)
  if (Number.isNaN(num)) return '¥0'
  const fixed = Math.round(num * 10) / 10
  return `¥${fixed % 1 === 0 ? fixed.toFixed(0) : fixed.toFixed(1)}`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

export function formatNumber(value: number | null | undefined): string {
  return Number(value ?? 0).toLocaleString('zh-CN')
}

const TIME_SLOT_LABELS: Record<string, string> = {
  morning: '上午',
  afternoon: '下午',
  evening: '晚上',
  noon: '中午',
}

export function timeSlotLabel(slot: string): string {
  return TIME_SLOT_LABELS[slot] ?? slot
}

const CATEGORY_LABELS: Record<string, string> = {
  sightseeing: '观光',
  nature: '自然',
  culture: '人文',
  food: '美食',
  shopping: '购物',
  entertainment: '娱乐',
  family: '亲子',
}

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category
}

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  confirmed: '已确认',
  shared: '已分享',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

export function durationText(minutes: number | null | undefined): string {
  const min = Number(minutes ?? 0)
  if (min <= 0) return '—'
  const hours = Math.floor(min / 60)
  const rest = min % 60
  if (hours && rest) return `${hours}小时${rest}分`
  if (hours) return `${hours}小时`
  return `${rest}分钟`
}

// 工具名 → 中文展示名
const TOOL_LABELS: Record<string, string> = {
  get_weather: '天气查询',
  search_poi: '景点检索',
  estimate_budget: '预算估算',
  plan_route: '路线规划',
}

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool
}
