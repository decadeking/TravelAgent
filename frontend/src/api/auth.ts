import { request } from './http'
import type { AuthResult, UserInfo } from '@/types'

export interface RegisterPayload {
  username: string
  password: string
  nickname: string
}

export interface LoginPayload {
  username: string
  password: string
}

export const authApi = {
  register: (payload: RegisterPayload) =>
    request<AuthResult>({ url: '/auth/register', method: 'post', data: payload }),
  login: (payload: LoginPayload) =>
    request<AuthResult>({ url: '/auth/login', method: 'post', data: payload }),
  me: () => request<UserInfo>({ url: '/users/me', method: 'get' }),
}
