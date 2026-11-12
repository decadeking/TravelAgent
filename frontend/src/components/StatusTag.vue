<script setup lang="ts">
import { computed } from 'vue'
import { statusLabel } from '@/utils/format'

const props = defineProps<{ status: string }>()

const cls = computed(() => {
  if (props.status === 'confirmed') return 'tag tag-confirmed'
  if (props.status === 'shared') return 'tag tag-shared'
  return 'tag tag-draft'
})
</script>

<template>
  <span :class="cls">{{ statusLabel(status) }}</span>
</template>
