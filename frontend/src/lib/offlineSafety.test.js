import { describe, expect, it } from 'vitest'
import { offlineSafetyMessage } from './offlineSafety'
import { LABELS } from '../constants/i18n'

describe('offlineSafetyMessage', () => {
  it('returns null for cacheable reference content (no stub needed)', () => {
    const adv = { response_type: 'informational', products_rates: [], warnings: [], problem_summary: 'Rice blast basics.' }
    expect(offlineSafetyMessage(adv, 'en')).toBeNull()
  })

  it('returns verify title/body + advisory escalation for time-sensitive content', () => {
    const adv = { response_type: 'diagnostic', products_rates: [{ product: 'Engenia', rate: '12.8 oz/A' }], warnings: [], escalation: 'Contact Craighead County Agent — Jane Doe — 870-555-0100' }
    const msg = offlineSafetyMessage(adv, 'en')
    expect(msg.title).toBe(LABELS.en.offlineVerifyTitle)
    expect(msg.body).toBe(LABELS.en.offlineVerifyBody)
    expect(msg.escalation).toContain('Craighead County Agent')
  })

  it('falls back to the generic Extension contact when no escalation present', () => {
    const adv = { response_type: 'diagnostic', products_rates: [], warnings: ['Do not spray during inversion.'], escalation: null }
    const msg = offlineSafetyMessage(adv, 'es')
    expect(msg.title).toBe(LABELS.es.offlineVerifyTitle)
    expect(msg.escalation).toBe(LABELS.es.offlineEscalationFallback)
  })
})
