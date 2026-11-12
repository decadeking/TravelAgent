<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import AppIcon from './AppIcon.vue'
import type { GeoPoint, MapMarker } from '@/types'

const props = withDefaults(
  defineProps<{
    center?: GeoPoint | null
    markers?: MapMarker[]
    height?: number
  }>(),
  { center: null, markers: () => [], height: 260 },
)

// 地图可用性上报：瓦片加载失败或没有点位时，父级据此收起整块区域，避免占地方
const emit = defineEmits<{ (e: 'available', value: boolean): void }>()

const container = ref<HTMLElement | null>(null)
let map: L.Map | null = null
let layer: L.LayerGroup | null = null

const hasData = computed(() => props.markers.length > 0 || Boolean(props.center))

// 瓦片不可达（离线/被墙）时降级为点位列表，避免空白地图
const tilesFailed = ref(false)
let tileErrors = 0
let tileOk = false

const mapUsable = computed(() => hasData.value && !tilesFailed.value)

watch(mapUsable, (v) => emit('available', v), { immediate: true })

function markerIcon(index: number): L.DivIcon {
  return L.divIcon({
    className: 'plan-map-marker',
    html: `<span>${index + 1}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -12],
  })
}

function render() {
  if (!map || !layer) return
  map.invalidateSize()
  layer.clearLayers()

  props.markers.forEach((point, index) => {
    const marker = L.marker([point.lat, point.lon], { icon: markerIcon(index) })
    const content = point.meta
      ? `<strong>${point.label}</strong><br/><span>${point.meta}</span>`
      : `<strong>${point.label}</strong>`
    marker.bindPopup(content)
    marker.addTo(layer as L.LayerGroup)
  })

  if (props.markers.length > 1) {
    const bounds = L.latLngBounds(props.markers.map((p) => [p.lat, p.lon] as [number, number]))
    map.fitBounds(bounds, { padding: [36, 36], maxZoom: 13 })
  } else if (props.markers.length === 1) {
    const point = props.markers[0]
    map.setView([point.lat, point.lon], 13)
  } else if (props.center) {
    map.setView([props.center.lat, props.center.lon], 11)
  }
}

onMounted(() => {
  if (!container.value) return
  const initialCenter: L.LatLngExpression = props.center
    ? [props.center.lat, props.center.lon]
    : [34.2, 108.9]
  map = L.map(container.value, {
    center: initialCenter,
    zoom: 11,
    zoomControl: true,
    attributionControl: true,
    scrollWheelZoom: false,
  })
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap',
  })
    .on('tileload', () => {
      tileOk = true
    })
    .on('tileerror', () => {
      tileErrors += 1
      if (!tileOk && tileErrors >= 4) tilesFailed.value = true
    })
    .addTo(map)
  layer = L.layerGroup().addTo(map)
  render()
  setTimeout(() => map?.invalidateSize(), 120)
})

watch(
  () => [props.center, props.markers],
  () => render(),
  { deep: true },
)

onBeforeUnmount(() => {
  map?.remove()
  map = null
  layer = null
})
</script>

<template>
  <!-- 能显示才占位：容器常挂载（保证 Leaflet 生命周期），不可用时整块 display:none -->
  <div
    class="map-wrap"
    :class="{ 'is-hidden': !mapUsable }"
    :style="mapUsable ? { height: `${height}px` } : undefined"
  >
    <div ref="container" class="map-canvas" />
    <div v-if="markers.length" class="map-badge">
      <AppIcon name="layers" :size="13" />
      {{ markers.length }} 个点位
    </div>
  </div>
  <div v-if="!mapUsable" class="map-note">
    <AppIcon name="map-pin" :size="13" />
    <span>{{ hasData ? '当前网络无法加载地图瓦片（坐标仍然真实）' : '暂无可展示的坐标点位' }}</span>
  </div>
</template>

<style scoped>
.map-wrap {
  position: relative;
  width: 100%;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
  background: #eef1f5;
}

.map-wrap.is-hidden {
  display: none;
}

.map-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 11px;
  border: 1px dashed var(--border);
  border-radius: 9px;
  background: var(--panel-soft);
  color: var(--text-faint);
  font-size: 12px;
}

.map-canvas {
  width: 100%;
  height: 100%;
}

.map-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 100%;
  padding: 20px;
  color: var(--text-faint);
  text-align: center;
}

.map-empty p {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
}

.map-empty span {
  font-size: 12px;
}

.map-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--text-muted);
  font-size: 11.5px;
  box-shadow: var(--shadow-card);
}

.map-points {
  height: 100%;
  overflow: auto;
  padding: 12px 14px;
  background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
}

.points-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  color: var(--text-muted);
  font-size: 12px;
}

.points-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.points-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--border);
  font-size: 12.5px;
}

.pt-idx {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--grad-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.pt-label {
  font-weight: 600;
}

.pt-meta {
  color: var(--text-faint);
}

.pt-coord {
  margin-left: auto;
  color: var(--text-faint);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
</style>

<style>
.plan-map-marker {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50% 50% 50% 0;
  transform: rotate(-45deg);
  background: linear-gradient(135deg, #6366f1, #3b82f6);
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.45);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.plan-map-marker span {
  transform: rotate(45deg);
}

.leaflet-popup-content {
  font-family: var(--font);
  font-size: 12.5px;
  line-height: 1.6;
}
</style>
