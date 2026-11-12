import axios, { type AxiosRequestConfig, type AxiosResponse } from 'axios'

export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

export class ApiError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

const TOKEN_KEY = 'ta_access_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

let unauthorizedHandler: (() => void) | null = null

export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler
}

export const http = axios.create({ baseURL: '/api', timeout: 60000 })

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => {
    const payload = resp.data as ApiEnvelope<unknown>
    if (payload && typeof payload === 'object' && 'code' in payload) {
      if (payload.code === 0) return payload.data as unknown as AxiosResponse
      throw new ApiError(payload.code, payload.message || '请求失败')
    }
    return resp
  },
  (error) => {
    const status: number | undefined = error?.response?.status
    const body = error?.response?.data as ApiEnvelope<unknown> | undefined
    if (status === 401) {
      clearToken()
      unauthorizedHandler?.()
      return Promise.reject(
        new ApiError(body?.code ?? 40101, body?.message || '登录状态已失效，请重新登录'),
      )
    }
    const message = body?.message || (error?.message as string) || '网络异常，请稍后重试'
    return Promise.reject(new ApiError(body?.code ?? status ?? -1, message))
  },
)

export function request<T>(config: AxiosRequestConfig): Promise<T> {
  return http.request(config) as unknown as Promise<T>
}
