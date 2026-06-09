import { describe, expect, it } from 'vitest'
import { isCacheableAsReference } from './offlineTiering'

const informational = {
  response_type: 'informational',
  products_rates: [],
  warnings: [],
  problem_summary: 'Rice blast is a fungal disease caused by Magnaporthe oryzae.',
  recommended_actions: ['Scout fields regularly for lesions.'],
}

describe('isCacheableAsReference', () => {
  it('caches a clean informational advisory with no rates/warnings', () => {
    expect(isCacheableAsReference(informational)).toBe(true)
  })

  it('refuses anything with product rates', () => {
    expect(isCacheableAsReference({ ...informational, products_rates: [{ product: 'Engenia', rate: '12.8 oz/A' }] })).toBe(false)
  })

  it('refuses anything with warnings', () => {
    expect(isCacheableAsReference({ ...informational, warnings: ['Do not spray during an inversion.'] })).toBe(false)
  })

  it('refuses diagnostic advisories', () => {
    expect(isCacheableAsReference({ ...informational, response_type: 'diagnostic' })).toBe(false)
  })

  it('refuses spray/timing keyword content even if informational', () => {
    expect(isCacheableAsReference({ ...informational, problem_summary: 'Apply dicamba within the spray window.' })).toBe(false)
  })

  it('defaults to false on missing/garbage input', () => {
    expect(isCacheableAsReference(null)).toBe(false)
    expect(isCacheableAsReference({})).toBe(false)
  })
})
