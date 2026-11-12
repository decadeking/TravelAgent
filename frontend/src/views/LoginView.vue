<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import { ApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

type Tab = 'login' | 'register'
const tab = ref<Tab>('login')
const error = ref('')
const submitting = ref(false)

const form = reactive({
  username: '',
  password: '',
  nickname: '',
})

const isRegister = computed(() => tab.value === 'register')

function switchTab(next: Tab) {
  tab.value = next
  error.value = ''
}

function validate(): string {
  if (!form.username.trim()) return '请输入用户名'
  if (form.username.trim().length < 3) return '用户名至少 3 个字符'
  if (!form.password) return '请输入密码'
  if (form.password.length < 6) return '密码至少 6 位'
  if (isRegister.value && !form.nickname.trim()) return '请输入昵称'
  return ''
}

async function submit() {
  error.value = ''
  const message = validate()
  if (message) {
    error.value = message
    return
  }
  submitting.value = true
  try {
    if (isRegister.value) {
      await auth.register(form.username.trim(), form.password, form.nickname.trim())
    } else {
      await auth.login(form.username.trim(), form.password)
    }
    const redirect = (route.query.redirect as string) || '/feed'
    router.replace(redirect)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '操作失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth">
    <div class="auth-visual">
      <div class="visual-inner">
        <div class="visual-brand">
          <span class="visual-mark">
            <AppIcon name="compass" :size="20" />
          </span>
          <div>
            <div class="visual-name">旅行吧 TravelAgent</div>
            <div class="visual-sub">智能体驱动的旅行规划</div>
          </div>
        </div>

        <h2 class="visual-title">把一句旅行想法<br />变成一份可落地的行程</h2>
        <p class="visual-desc">
          多轮对话式修订、实时行程预览、预算与天气工具协同 —— 你的专属旅行规划智能体。
        </p>

        <ul class="visual-points">
          <li><AppIcon name="check" :size="14" /> 工具调用过程透明可见</li>
          <li><AppIcon name="check" :size="14" /> 按天时间轴实时增量刷新</li>
          <li><AppIcon name="check" :size="14" /> 预算超支自动提示与调整</li>
        </ul>
      </div>
    </div>

    <div class="auth-panel">
      <div class="auth-card">
        <div class="auth-head">
          <h1>{{ isRegister ? '创建账户' : '欢迎回来' }}</h1>
          <p class="muted">{{ isRegister ? '注册后即可开始规划你的旅行' : '登录以继续你的旅行规划' }}</p>
        </div>

        <div class="tabs" role="tablist">
          <button
            class="tab"
            :class="{ 'is-active': tab === 'login' }"
            type="button"
            role="tab"
            @click="switchTab('login')"
          >
            登录
          </button>
          <button
            class="tab"
            :class="{ 'is-active': tab === 'register' }"
            type="button"
            role="tab"
            @click="switchTab('register')"
          >
            注册
          </button>
        </div>

        <form class="auth-form" @submit.prevent="submit">
          <label class="field">
            <span class="field-label">用户名</span>
            <input v-model="form.username" class="input" type="text" placeholder="请输入用户名" autocomplete="username" />
          </label>

          <label v-if="isRegister" class="field">
            <span class="field-label">昵称</span>
            <input v-model="form.nickname" class="input" type="text" placeholder="想让我们怎么称呼你" />
          </label>

          <label class="field">
            <span class="field-label">密码</span>
            <input
              v-model="form.password"
              class="input"
              type="password"
              placeholder="至少 6 位"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
            />
          </label>

          <Transition name="fade">
            <div v-if="error" class="alert">
              <AppIcon name="alert" :size="14" />
              <span>{{ error }}</span>
            </div>
          </Transition>

          <button class="btn btn-primary submit" type="submit" :disabled="submitting">
            <span v-if="submitting" class="spinner" />
            <span>{{ submitting ? '处理中…' : isRegister ? '注册并进入' : '登录' }}</span>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth {
  display: grid;
  grid-template-columns: minmax(360px, 1fr) minmax(360px, 1fr);
  min-height: 100vh;
  background: var(--bg);
}

.auth-visual {
  position: relative;
  display: flex;
  align-items: center;
  padding: 56px;
  background: radial-gradient(1200px 600px at 10% 10%, #eef2ff 0%, #f7f8fa 55%),
    linear-gradient(160deg, #eef4ff 0%, #f7f8fa 100%);
  border-right: 1px solid var(--border);
}

.visual-inner {
  max-width: 420px;
}

.visual-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 40px;
}

.visual-mark {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--grad-primary);
  color: #fff;
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.3);
}

.visual-name {
  font-size: 15px;
  font-weight: 600;
}

.visual-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.visual-title {
  font-size: 28px;
  line-height: 1.4;
  letter-spacing: 0.2px;
  font-weight: 650;
}

.visual-desc {
  margin-top: 14px;
  font-size: 13.5px;
  color: var(--text-muted);
  line-height: 1.8;
}

.visual-points {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 28px;
}

.visual-points li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text);
}

.visual-points svg {
  color: var(--success);
}

.auth-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
}

.auth-card {
  width: 100%;
  max-width: 380px;
  padding: 28px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.auth-head h1 {
  font-size: 20px;
  font-weight: 650;
}

.auth-head p {
  margin-top: 6px;
  font-size: 13px;
}

.tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin: 22px 0 20px;
  padding: 4px;
  border-radius: 11px;
  background: #f2f4f7;
}

.tab {
  height: 34px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-weight: 500;
  transition: background 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.tab.is-active {
  background: #fff;
  color: var(--text);
  box-shadow: var(--shadow-card);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.alert {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12.5px;
}

.submit {
  margin-top: 4px;
  height: 42px;
}

@media (max-width: 860px) {
  .auth {
    grid-template-columns: 1fr;
  }

  .auth-visual {
    display: none;
  }
}
</style>
