import { request } from './http'
import type { TripCreatePayload, TripDetail, TripListResult, TripStatus } from '@/types'

export interface TripListQuery {
  page?: number
  page_size?: number
  status?: TripStatus | ''
}

export interface TripUpdatePayload extends Partial<TripCreatePayload> {
  version?: number
}

export const tripApi = {
  list: (params: TripListQuery = {}) =>
    request<TripListResult>({ url: '/trips', method: 'get', params }),
  detail: (id: number | string) => request<TripDetail>({ url: `/trips/${id}`, method: 'get' }),
  create: (payload: TripCreatePayload) =>
    request<TripDetail>({ url: '/trips', method: 'post', data: payload }),
  update: (id: number | string, payload: TripUpdatePayload) =>
    request<TripDetail>({ url: `/trips/${id}`, method: 'put', data: payload }),
  remove: (id: number | string) =>
    request<{ deleted: number }>({ url: `/trips/${id}`, method: 'delete' }),
}
