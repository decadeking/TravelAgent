// 原生 fetch 流式解析 SSE（支持 POST + Authorization 头，原生 EventSource 无法满足）

export interface SseRequest {
  url: string
  body: unknown
  token?: string | null
  signal?: AbortSignal
  lastEventId?: number
}

export type SseHandler = (event: string, data: unknown, eventId?: number) => void

const CLOSE_EVENT = '__close__'

function parseBlock(raw: string, onEvent: SseHandler): void {
  const normalized = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  let event = 'message'
  let eventId: number | undefined
  const dataLines: string[] = []
  for (const line of normalized.split('\n')) {
    if (line === '' || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') dataLines.push(value)
    else if (field === 'id') eventId = Number(value) || undefined
    else if (field === 'retry') { /* 服务端建议的重连间隔，由 streamSseWithRetry 使用 */ }
  }
  if (event === CLOSE_EVENT) return
  if (dataLines.length === 0 && event === 'message') return
  const dataStr = dataLines.join('\n')
  let parsed: unknown = dataStr
  if (dataStr) {
    try {
      parsed = JSON.parse(dataStr)
    } catch {
      parsed = dataStr
    }
  } else {
    parsed = null
  }
  onEvent(event, parsed, eventId)
}

/**
 * 发起一次 SSE 流式请求。函数在流结束或解析完成时 resolve。
 * 服务端为事件编号（id:），调用方可据此去重；lastEventId 用于重连续传提示。
 */
export async function streamSse(req: SseRequest, onEvent: SseHandler): Promise<void> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  if (req.token) headers.Authorization = `Bearer ${req.token}`
  if (req.lastEventId) headers['Last-Event-ID'] = String(req.lastEventId)

  let resp: Response
  try {
    resp = await fetch(req.url, {
      method: 'POST',
      headers,
      body: JSON.stringify(req.body),
      signal: req.signal,
    })
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') return
    throw new Error('无法连接到服务器，请确认后端服务已启动')
  }

  if (!resp.ok) {
    let message = `请求失败（HTTP ${resp.status}）`
    try {
      const payload = (await resp.json()) as { message?: string }
      if (payload?.message) message = payload.message
    } catch {
      /* 忽略非 JSON 错误体 */
    }
    throw new Error(message)
  }
  if (!resp.body) throw new Error('服务器未返回数据流')

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx = buffer.indexOf('\n\n')
      while (idx >= 0) {
        const block = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        if (block.trim()) parseBlock(block, onEvent)
        idx = buffer.indexOf('\n\n')
      }
    }
    buffer += decoder.decode()
    if (buffer.trim()) parseBlock(buffer, onEvent)
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') return
    throw err
  }
}

/**
 * 带指数退避重连的 SSE 请求（Q28）。
 * 网络中断时按 1s/2s/4s 退避重试，同一 request_id 由后端幂等挡住重复规划；
 * 每次重连通过 onStateRestore 回调让调用方先恢复会话上下文。
 */
export async function streamSseWithRetry(
  makeReq: (lastEventId: number) => SseRequest,
  onEvent: SseHandler,
  opts: { maxRetries?: number; onStateRestore?: () => Promise<void> } = {},
): Promise<void> {
  const maxRetries = opts.maxRetries ?? 3
  let lastEventId = 0
  let attempt = 0
  for (;;) {
    try {
      await streamSse(makeReq(lastEventId), (ev, data, id) => {
        if (id !== undefined && id > lastEventId) lastEventId = id
        onEvent(ev, data, id)
      })
      return
    } catch (err) {
      if (attempt >= maxRetries) throw err
      attempt += 1
      const delay = Math.min(8000, 1000 * 2 ** (attempt - 1))
      await new Promise((r) => setTimeout(r, delay))
      if (opts.onStateRestore) {
        try { await opts.onStateRestore() } catch { /* 恢复失败继续重试 */ }
      }
    }
  }
}
