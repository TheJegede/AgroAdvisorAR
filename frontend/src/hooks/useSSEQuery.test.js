import { beforeEach, describe, expect, it, vi } from 'vitest'
import { parseSSEPayload, beginRequest, fetchQueryWithAuth } from './useSSEQuery'

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
