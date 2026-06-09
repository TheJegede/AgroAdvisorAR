import { describe, expect, it, beforeEach } from 'vitest'
import { cacheReferenceAdvisory, getCachedAdvisories, MAX_CACHED } from './offlineCache'

function fakeStore() {
  const m = {}
  return {
    getItem: (k) => (k in m ? m[k] : null),
    setItem: (k, v) => { m[k] = String(v) },
  }
}

describe('offlineCache', () => {
  let store
  beforeEach(() => { store = fakeStore() })

  it('caches a reference advisory with a timestamp', () => {
    const adv = { response_type: 'informational', products_rates: [], warnings: [], problem_summary: 'Rice blast basics.' }
    cacheReferenceAdvisory(adv, { store, now: () => 1000 })
    const cached = getCachedAdvisories({ store })
    expect(cached).toHaveLength(1)
    expect(cached[0].cachedAt).toBe(1000)
    expect(cached[0].advisory.problem_summary).toBe('Rice blast basics.')
  })

  it('refuses to cache time-sensitive content', () => {
    const adv = { response_type: 'diagnostic', products_rates: [{ product: 'Engenia', rate: '12.8 oz/A' }], warnings: [] }
    cacheReferenceAdvisory(adv, { store, now: () => 1000 })
    expect(getCachedAdvisories({ store })).toHaveLength(0)
  })

  it('keeps only the last MAX_CACHED, newest first', () => {
    for (let i = 0; i < MAX_CACHED + 3; i++) {
      cacheReferenceAdvisory(
        { response_type: 'informational', products_rates: [], warnings: [], problem_summary: `ref ${i}` },
        { store, now: () => i },
      )
    }
    const cached = getCachedAdvisories({ store })
    expect(cached).toHaveLength(MAX_CACHED)
    expect(cached[0].advisory.problem_summary).toBe(`ref ${MAX_CACHED + 2}`) // newest first
  })
})
