import { request } from './http'
import type { DocUploadResult, KbDocItem, MediaAsset } from '@/types'

export type MediaKind = 'image' | 'avatar'

export const mediaApi = {
  upload: (file: File, kind: MediaKind = 'image') => {
    const form = new FormData()
    form.append('file', file)
    return request<MediaAsset>({
      url: `/media/upload?kind=${kind}`,
      method: 'post',
      data: form,
    })
  },
  mine: () => request<MediaAsset[]>({ url: '/media/mine/list', method: 'get' }),
  /** 上传知识文档（pdf / wps(docx) / txt / md）→ 解析清洗 → 入 RAG 知识库 */
  uploadDoc: (file: File, city = '通用') => {
    const form = new FormData()
    form.append('file', file)
    return request<DocUploadResult>({
      url: `/media/upload_doc?city=${encodeURIComponent(city)}`,
      method: 'post',
      data: form,
    })
  },
  /** 已入库的知识文档列表 */
  myDocs: () => request<KbDocItem[]>({ url: '/media/doc/list', method: 'get' }),
}
