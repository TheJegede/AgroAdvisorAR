import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearAuthStorage,
  getAccessToken,
  getRefreshToken,
  refreshAuthToken,
  setAuthTokens,
} from './authTokens'

function makeStorage() {
  const values = new Map()
  return {
    getItem: vi.fn((key) => values.get(key) ?? null),
    setItem: vi.fn((key, value) => values.set(key, value)),
    removeItem: vi.fn((key) => values.delete(key)),
  }
}

describe('auth token helpers', () => {
  let localStore

  beforeEach(() => {
    vi.unstubAllGlobals()
    localStore = makeStorage()
    vi.stubGlobal('localStorage', localStore)
  })

  it('stores, reads, and clears auth tokens', () => {
    setAuthTokens('access', 'refresh')

    expect(getAccessToken()).toBe('access')
    expect(getRefreshToken()).toBe('refresh')

    clearAuthStorage()

    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  it('coalesces concurrent refresh requests', async () => {
    setAuthTokens('old-access', 'refresh')
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        access_token: 'new-access',
        refresh_token: 'new-refresh',
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await Promise.all([refreshAuthToken(), refreshAuthToken()])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(getAccessToken()).toBe('new-access')
    expect(getRefreshToken()).toBe('new-refresh')
  })
})
