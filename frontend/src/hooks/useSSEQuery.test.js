import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  parseSSEPayload,
  beginRequest,
  fetchQueryWithAuth,
  consumeSSEStream,
} from './useSSEQuery'

function makeStorage() {
  const values = new Map()
  return {
    getItem: vi.fn((key) => values.get(key) ?? null),
    setItem: vi.fn((key, value) => values.set(key, value)),
    removeItem: vi.fn((key) => values.delete(key)),
  }
}

describe('fetchQueryWithAuth', () => {
  let localStore

  beforeEach(() => {
    vi.unstubAllGlobals()
    localStore = makeStorage()
    localStore.setItem('access_token', 'old-access')
    vi.stubGlobal('localStorage', localStore)
    vi.stubGlobal('window', { location: { href: '' } })
  })

  it('refreshes and retries the query once after a 401', async () => {
    localStore.setItem('refresh_token', 'refresh-token')
    let queryCalls = 0
    const fetchMock = vi.fn(async (url) => {
      if (url === '/api/v1/query') {
        queryCalls += 1
        return queryCalls === 1 ? { ok: false, status: 401 } : { ok: true, status: 200 }
      }
      if (url === '/api/v1/auth/refresh') {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            access_token: 'new-access',
            refresh_token: 'new-refresh',
          }),
        }
      }
      return { ok: true, status: 200 }
    })
    vi.stubGlobal('fetch', fetchMock)

    const res = await fetchQueryWithAuth({
      payload: { message: 'rice question' },
      signal: undefined,
    })

    expect(res.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(queryCalls).toBe(2)
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe('Bearer new-access')
  })

  it('clears auth storage and redirects when refresh is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401 })))

    const res = await fetchQueryWithAuth({
      payload: { message: 'rice question' },
      signal: undefined,
    })

    expect(res).toBeNull()
    expect(localStore.removeItem).toHaveBeenCalledWith('access_token')
    expect(localStore.removeItem).toHaveBeenCalledWith('refresh_token')
    expect(window.location.href).toBe('/login')
  })
})

describe('beginRequest', () => {
  it('aborts the previous controller before assigning a new one', () => {
    const ref = { current: null }
    const first = beginRequest(ref)
    const second = beginRequest(ref)

    expect(first.signal.aborted).toBe(true)
    expect(second.signal.aborted).toBe(false)
    expect(ref.current).toBe(second)
  })

  it('is a no-op on the first request (no prior controller)', () => {
    const ref = { current: null }
    const controller = beginRequest(ref)
    expect(controller.signal.aborted).toBe(false)
    expect(ref.current).toBe(controller)
  })
})

describe('parseSSEPayload', () => {
  it('parses streamed error envelopes instead of treating them as keepalives', () => {
    const { parsed, malformed } = parseSSEPayload('{"error":"RAG failed"}')

    expect(malformed).toBe(false)
    expect(parsed.error).toBe('RAG failed')
  })

  it('marks malformed keepalive payloads as malformed', () => {
    const { parsed, malformed } = parseSSEPayload(': keepalive')

    expect(malformed).toBe(true)
    expect(parsed).toBeNull()
  })
})

function readerFrom(chunks) {
  const enc = new TextEncoder()
  let i = 0
  return {
    read: async () =>
      i < chunks.length
        ? { done: false, value: enc.encode(chunks[i++]) }
        : { done: true, value: undefined },
  }
}

describe('consumeSSEStream', () => {
  it('delivers an advisory and reports delivered=true', async () => {
    const onResult = vi.fn()
    const reader = readerFrom([
      `data: ${JSON.stringify({ advisory: { problem_summary: 'ok' }, message_id: 'm1', category: 'IN_SCOPE_RICE:DIAG' })}\n\n`,
      'data: [DONE]\n\n',
    ])

    const delivered = await consumeSSEStream(reader, { onResult })

    expect(delivered).toBe(true)
    expect(onResult).toHaveBeenCalledWith({ problem_summary: 'ok' }, 'm1', 'IN_SCOPE_RICE:DIAG')
  })

  it('reports delivered=false when the stream is only [DONE]', async () => {
    const onResult = vi.fn()
    const reader = readerFrom(['data: [DONE]\n\n'])

    const delivered = await consumeSSEStream(reader, { onResult })

    expect(delivered).toBe(false)
    expect(onResult).not.toHaveBeenCalled()
  })

  it('reports delivered=false when the connection closes with nothing', async () => {
    const onResult = vi.fn()
    const reader = readerFrom([': keepalive\n\n', ': keepalive\n\n'])

    const delivered = await consumeSSEStream(reader, { onResult })

    expect(delivered).toBe(false)
    expect(onResult).not.toHaveBeenCalled()
  })

  it('throws on a streamed error frame', async () => {
    const reader = readerFrom([`data: ${JSON.stringify({ error: 'RAG failed' })}\n\n`])

    await expect(consumeSSEStream(reader, { onResult: vi.fn() })).rejects.toThrow('RAG failed')
  })

  it('routes progress frames to onProgress, advisory to onResult', async () => {
    const progress = []
    const results = []
    const reader = readerFrom([
      'data: {"progress":{"stage":"searching"}}\n\n',
      'data: {"progress":{"stage":"sources_found","count":2,"titles":["A","B"]}}\n\n',
      'data: {"advisory":{"problem_summary":"ok"},"message_id":"m1","category":"IN_SCOPE_RICE:DIAG"}\n\n',
      'data: [DONE]\n\n',
    ])
    const delivered = await consumeSSEStream(reader, {
      onResult: (a) => results.push(a),
      onProgress: (p) => progress.push(p),
    })
    expect(progress.map((p) => p.stage)).toEqual(['searching', 'sources_found'])
    expect(progress[1].titles).toEqual(['A', 'B'])
    expect(results).toHaveLength(1)
    expect(delivered).toBe(true)
  })

  it('never renders a stray stage/non-advisory frame as a card', async () => {
    const results = []
    const progress = []
    const reader = readerFrom([
      // A bare stage frame (no "progress" wrapper) — must route to onProgress, not onResult.
      'data: {"stage":"writing"}\n\n',
      // An empty object — must be ignored, never an empty advisory card.
      'data: {}\n\n',
      'data: {"advisory":{"problem_summary":"ok"},"message_id":"m1"}\n\n',
      'data: [DONE]\n\n',
    ])
    const delivered = await consumeSSEStream(reader, {
      onResult: (a) => results.push(a),
      onProgress: (p) => progress.push(p),
    })
    expect(results).toEqual([{ problem_summary: 'ok' }])
    expect(progress.map((p) => p.stage)).toEqual(['writing'])
    expect(delivered).toBe(true)
  })

  it('progress-only stream reports delivered=false (retry surfaces)', async () => {
    const reader = readerFrom([
      'data: {"progress":{"stage":"searching"}}\n\n',
      'data: [DONE]\n\n',
    ])
    const delivered = await consumeSSEStream(reader, { onResult: () => {}, onProgress: () => {} })
    expect(delivered).toBe(false)
  })
})
