<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import AppIcon from './AppIcon.vue'

withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    wide?: boolean
  }>(),
  { subtitle: '', wide: false },
)

const emit = defineEmits<{ (e: 'close'): void }>()

function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', onKey)
  document.body.style.overflow = 'hidden'
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div class="mask" @click.self="emit('close')">
      <div class="box" :class="{ 'is-wide': wide }" role="dialog" aria-modal="true">
        <header class="box-head">
          <div class="box-head-text">
            <h3>{{ title }}</h3>
            <p v-if="subtitle">{{ subtitle }}</p>
          </div>
          <button class="box-close" type="button" title="关闭" @click="emit('close')">
            <AppIcon name="close" :size="18" />
          </button>
        </header>
        <div class="box-body">
          <slot />
        </div>
        <footer v-if="$slots.footer" class="box-foot">
          <slot name="footer" />
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 6vh 16px 24px;
  overflow-y: auto;
  background: rgba(17, 24, 39, 0.4);
  backdrop-filter: blur(2px);
}

.box {
  width: 100%;
  max-width: 480px;
  background: #fff;
  border-radius: var(--radius-lg);
  box-shadow: 0 24px 60px rgba(17, 24, 39, 0.24);
  animation: pop 0.16s ease;
}

.box.is-wide {
  max-width: 680px;
}

@keyframes pop {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.99);
  }
}

.box-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border-soft);
}

.box-head h3 {
  font-size: 16px;
  font-weight: 650;
}

.box-head p {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--text-muted);
}

.box-close {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  transition: background 0.15s ease, color 0.15s ease;
}

.box-close:hover {
  background: #f1f3f6;
  color: var(--text);
}

.box-body {
  padding: 18px 20px;
}

.box-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--border-soft);
}
</style>
