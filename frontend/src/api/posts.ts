import { request } from './http'
import type {
  CityChip,
  FriendFeedResult,
  MyComment,
  PostComment,
  PostDetail,
  PostListResult,
  PostPayload,
  PostSummary,
} from '@/types'

export interface PostListQuery {
  page?: number
  page_size?: number
  city?: string
  sort?: 'new' | 'hot'
  mine?: boolean
  author_id?: number
}

export interface LikeResult {
  liked: boolean
  like_count: number
  heat?: number
}

export interface CollectResult {
  collected: boolean
  collect_count: number
  heat?: number
}

export const postApi = {
  list: (params: PostListQuery = {}) =>
    request<PostListResult>({ url: '/posts', method: 'get', params }),
  /** 动态流：我关注的人 + 我自己的动态 */
  moments: (params: { page?: number; page_size?: number } = {}) =>
    request<FriendFeedResult>({ url: '/posts/friends', method: 'get', params }),
  cities: () => request<CityChip[]>({ url: '/posts/cities', method: 'get' }),
  detail: (id: number | string) => request<PostDetail>({ url: `/posts/${id}`, method: 'get' }),
  create: (payload: PostPayload) => request<PostDetail>({ url: '/posts', method: 'post', data: payload }),
  update: (id: number | string, payload: PostPayload) =>
    request<PostDetail>({ url: `/posts/${id}`, method: 'put', data: payload }),
  remove: (id: number | string) =>
    request<{ deleted: number }>({ url: `/posts/${id}`, method: 'delete' }),
  like: (id: number | string) =>
    request<LikeResult>({ url: `/posts/${id}/like`, method: 'post' }),
  collect: (id: number | string) =>
    request<CollectResult>({ url: `/posts/${id}/collect`, method: 'post' }),
  comment: (id: number | string, content: string) =>
    request<PostComment>({ url: `/posts/${id}/comments`, method: 'post', data: { content } }),
  updateComment: (id: number | string, content: string) =>
    request<{ id: number; content: string }>({
      url: `/posts/comments/${id}`, method: 'put', data: { content },
    }),
  removeComment: (id: number | string) =>
    request<{ deleted: number }>({ url: `/posts/comments/${id}`, method: 'delete' }),
  collections: () => request<PostSummary[]>({ url: '/posts/mine/collections', method: 'get' }),
  myComments: () => request<MyComment[]>({ url: '/posts/mine/comments', method: 'get' }),
}
