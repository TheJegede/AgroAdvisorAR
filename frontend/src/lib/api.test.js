import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import api from './api'

function makeStorage() {
  const values = new Map()
  return {
    getItem: vi.fn((key) => values.get(key) ?? null),
    setItem: vi.fn((key, value) => values.set(key, value)),
    removeItem: vi.fn((key) => values.delete(key)),
  }
}

describe('api auth interceptor', () => {
  const originalAdapter = api.defaults.adapter

  beforeEach(() => {
    vi.unstubAllGlobals()
    const localStore = makeStorage()
    localStore.setItem('access_token', 'old-access')
    localStore.setItem('refresh_token', 'refresh-token')
    vi.stubGlobal('localStorage', localStore)
  })

  afterEach(() => {
    api.defaults.adapter = originalAdapter
  })

  it('refreshes once and retries a 401 non-auth request', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        access_token: 'new-access',
        refresh_token: 'new-refresh',
      }),
    })))

    let adapterCalls = 0
    const adapter = vi.fn(async (config) => {
      adapterCalls += 1
      if (adapterCalls === 1) {
        return Promise.reject({
          config,
          response: { status: 401 },
        })
      }
      return {
        config,
        data: { ok: true },
        headers: {},
        status: 200,
        statusText: 'OK',
      }
    })
    api.defaults.adapter = adapter

    const response = await api.get('/profile')

    expect(response.data).toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledWith('/api/v1/auth/refresh', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ refresh_token: 'refresh-token' }),
    }))
    expect(adapter).toHaveBeenCalledTimes(2)
    expect(adapter.mock.calls[1][0].headers.Authorization).toBe('Bearer new-access')
  })
})
