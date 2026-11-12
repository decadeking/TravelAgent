<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { adminApi } from '@/api/admin'
import { ApiError } from '@/api/http'
import type { MediaStats, MediaSyncResult } from '@/types'

const stats = ref<MediaStats | null>(null)
const syncResult = ref<MediaSyncResult | null>(null)
const loading = ref(true)
const syncing = ref(false)
const error = ref('')
const flash = ref('')

function notify(text: string) {
  flash.value = text
  window.setTimeout(() => {
    flash.value = ''
  }, 3000)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    stats.value = await adminApi.mediaStats()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '加载图片资源失败'
  } finally {
    loading.value = false
  }
}

async function sync() {
  syncing.value = true
  error.value = ''
  try {
    syncResult.value = await adminApi.syncMedia()
    notify('外链图片同步完成')
    await load()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '同步失败'
  } finally {
    syncing.value = false
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

    <section class="card block">
      <header class="block-head">
        <div>
          <h4><AppIcon name="image" :size="15" /> 图片资源</h4>
          <p>图片二进制已存入数据库，由 media-service 提供访问。</p>
        </div>
        <button class="btn btn-ghost btn-sm" type="button" :disabled="loading" @click="load">
          <AppIcon name="refresh" :size="14" />
          刷新
        </button>
      </header>

      <div v-if="loading" class="skeleton" style="height: 84px" />

      <div v-else class="media-stats">
        <div class="stat-cell">
          <AppIcon name="image" :size="16" />
          <span class="stat-num">{{ (stats?.count ?? 0).toLocaleString('zh-CN') }}</span>
          <span class="stat-label">图片数量</span>
        </div>
        <div class="stat-cell">
          <AppIcon name="database" :size="16" />
          <span class="stat-num">{{ (stats?.mb ?? 0).toLocaleString('zh-CN') }}</span>
          <span class="stat-label">占用体积 (MB)</span>
        </div>
      </div>

      <div class="block-foot">
        <button class="btn btn-primary btn-sm" type="button" :disabled="syncing" @click="sync">
          <span v-if="syncing" class="spinner" />
          <AppIcon v-else name="upload" :size="14" />
          {{ syncing ? '同步中…' : '同步外链图片入库' }}
        </button>
      </div>
    </section>

    <section v-if="syncResult" class="card block">
      <header class="block-head">
        <h4><AppIcon name="check" :size="15" /> 同步结果</h4>
      </header>
      <ul class="kv">
        <li>
          <span class="kv-key">图片入库</span>
          <span class="kv-val">{{ syncResult.images_stored }}</span>
        </li>
        <li>
          <span class="kv-key">头像入库</span>
          <span class="kv-val">{{ syncResult.avatars_stored }}</span>
        </li>
        <li>
          <span class="kv-key">失败数</span>
          <span class="kv-val">{{ syncResult.failed }}</span>
        </li>
        <li>
          <span class="kv-key">媒体总数</span>
          <span class="kv-val">{{ syncResult.media_total }}</span>
        </li>
      </ul>
    </section>
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

.block {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.block-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.block-head h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14.5px;
  font-weight: 650;
}

.block-head p {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.media-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.stat-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid var(--border);
  color: var(--primary-strong);
}

.stat-num {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
}

.stat-label {
  font-size: 12.5px;
  color: var(--text-muted);
}

.block-foot {
  display: flex;
  justify-content: flex-end;
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
}

.kv-val {
  font-weight: 600;
}

@media (max-width: 680px) {
  .media-stats {
    grid-template-columns: 1fr;
  }
}
</style>