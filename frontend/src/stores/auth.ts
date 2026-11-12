import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import { clearToken, getToken, setToken } from '@/api/http'
import type { UserInfo } from '@/types'

interface AuthState {
  token: string
  user: UserInfo | null
  loading: boolean
  initialized: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: getToken(),
    user: null,
    loading: false,
    initialized: false,
  }),
  getters: {
    isLoggedIn: (state): boolean => Boolean(state.token),
    isAdmin: (state): boolean => state.user?.role === 'admin',
    displayName: (state): string => state.user?.nickname || state.user?.username || '旅行者',
    avatarText: (state): string => {
      const name = state.user?.nickname || state.user?.username || '旅'
      return name.trim().slice(0, 1).toUpperCase()
    },
  },
  actions: {
    applyAuth(token: string, user: UserInfo) {
      this.token = token
      this.user = user
      this.initialized = true
      setToken(token)
    },
    setUser(user: UserInfo) {
      this.user = user
    },
    async login(username: string, password: string) {
      this.loading = true
      try {
        const res = await authApi.login({ username, password })
        this.applyAuth(res.access_token, res.user)
        return res
      } finally {
        this.loading = false
      }
    },
    async register(username: string, password: string, nickname: string) {
      this.loading = true
      try {
        const res = await authApi.register({ username, password, nickname })
        this.applyAuth(res.access_token, res.user)
        return res
      } finally {
        this.loading = false
      }
    },
    async fetchMe() {
      if (!this.token) return null
      this.loading = true
      try {
        this.user = await authApi.me()
        this.initialized = true
        return this.user
      } finally {
        this.loading = false
      }
    },
    logout() {
      this.token = ''
      this.user = null
      this.initialized = false
      clearToken()
    },
  },
})
