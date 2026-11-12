import { request } from './http'
import type {
  FriendCard,
  ModelConfigSaveResult,
  ModelTestResult,
  UsageInfo,
  UserInfo,
  UserModelConfig,
  UserPublic,
} from '@/types'

export interface ProfilePayload {
  nickname?: string
  avatar?: string
  cover?: string
  bio?: string
}

export interface ModelConfigPayload {
  api_key?: string
  model?: string
  clear_api_key?: boolean
}

export const userApi = {
  getPreferences: () => request<Record<string, string>>({ url: '/users/preferences', method: 'get' }),
  savePreferences: (preferences: Record<string, string>) =>
    request<Record<string, string>>({
      url: '/users/preferences',
      method: 'put',
      data: { preferences },
    }),
  getUsage: () => request<UsageInfo>({ url: '/users/usage', method: 'get' }),
  updateMe: (payload: ProfilePayload) =>
    request<UserInfo>({ url: '/users/me', method: 'put', data: payload }),
  getModelConfig: () => request<UserModelConfig>({ url: '/users/model-config', method: 'get' }),
  saveModelConfig: (payload: ModelConfigPayload) =>
    request<ModelConfigSaveResult>({ url: '/users/model-config', method: 'put', data: payload }),
  testModelConfig: (payload: { api_key?: string; model?: string }) =>
    request<ModelTestResult>({ url: '/users/model-config/test', method: 'post', data: payload }),
  // 关注 / 好友
  friends: () => request<FriendCard[]>({ url: '/users/friends', method: 'get' }),
  following: () => request<FriendCard[]>({ url: '/users/following', method: 'get' }),
  followers: () => request<FriendCard[]>({ url: '/users/followers', method: 'get' }),
  discover: () => request<FriendCard[]>({ url: '/users/discover', method: 'get' }),
  userProfile: (id: number) => request<UserPublic>({ url: `/users/${id}`, method: 'get' }),
  toggleFollow: (id: number) =>
    request<{ following: boolean }>({ url: `/users/${id}/follow`, method: 'post' }),
}
