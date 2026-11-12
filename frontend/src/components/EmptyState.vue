<script setup lang="ts">
defineProps<{
  title: string
  description?: string
  actionText?: string
}>()

const emit = defineEmits<{ (e: 'action'): void }>()
</script>

<template>
  <div class="empty">
    <div class="empty-art" aria-hidden="true">
      <svg viewBox="0 0 120 96" width="132" height="106" fill="none">
        <rect x="10" y="18" width="100" height="64" rx="12" fill="#F1F4F9" />
        <rect x="18" y="30" width="46" height="7" rx="3.5" fill="#DDE3EC" />
        <rect x="18" y="44" width="66" height="7" rx="3.5" fill="#E7EBF2" />
        <rect x="18" y="58" width="38" height="7" rx="3.5" fill="#E7EBF2" />
        <circle cx="92" cy="66" r="16" fill="url(#g)" />
        <path
          d="M92 58.5c2.6 0 4.7 2.1 4.7 4.7 0 3.3-4.7 8.6-4.7 8.6s-4.7-5.3-4.7-8.6c0-2.6 2.1-4.7 4.7-4.7z"
          stroke="#fff"
          stroke-width="1.6"
          stroke-linejoin="round"
        />
        <circle cx="92" cy="63.2" r="1.5" fill="#fff" />
        <defs>
          <linearGradient id="g" x1="76" y1="50" x2="108" y2="82" gradientUnits="userSpaceOnUse">
            <stop stop-color="#6366F1" />
            <stop offset="1" stop-color="#3B82F6" />
          </linearGradient>
        </defs>
      </svg>
    </div>
    <h3 class="empty-title">{{ title }}</h3>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <button v-if="actionText" class="btn btn-primary" type="button" @click="emit('action')">
      {{ actionText }}
    </button>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  text-align: center;
}

.empty-art {
  margin-bottom: 4px;
}

.empty-title {
  font-size: 15px;
  font-weight: 600;
}

.empty-desc {
  max-width: 340px;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.7;
}

.empty .btn {
  margin-top: 6px;
}
</style>
