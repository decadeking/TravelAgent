import { request } from './http'
import type { PoiResult, WeatherResult } from '@/types'

export interface ReverseGeoResult {
  name: string
  city?: string
  district?: string
  lat: number
  lon: number
  source: string
  found: boolean
  display_name?: string
}

export const toolApi = {
  cities: () => request<string[]>({ url: '/tools/cities', method: 'get' }),
  weather: (city: string, days = 3) =>
    request<WeatherResult>({ url: '/tools/weather', method: 'get', params: { city, days } }),
  poi: (city: string, topk = 8) =>
    request<PoiResult>({ url: '/tools/poi', method: 'get', params: { city, topk } }),
  /** 逆地理编码：浏览器定位坐标 → 可读地名（地图地点 API） */
  reverseGeocode: (lat: number, lon: number) =>
    request<ReverseGeoResult>({ url: '/tools/reverse_geocode', method: 'get', params: { lat, lon } }),
}
