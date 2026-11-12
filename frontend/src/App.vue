<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const useLayout = computed(() => !route.meta.public)

onMounted(() => {
  if (auth.isLoggedIn && !auth.user) {
    auth.fetchMe().catch(() => {
      /* 令牌失效时由拦截器统一处理 */
    })
  }
})
</script>

<template>
  <AppLayout v-if="useLayout">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </AppLayout>
  <router-view v-else />
</template>
