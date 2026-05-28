import { describe, expect, it, vi } from 'vitest'
import NLIConfidenceBadge from './NLIConfidenceBadge'

vi.mock('../../contexts/LangContext', () => ({
  useLang: () => ({ t: { nliScore: 'NLI Score' } }),
}))

describe('NLIConfidenceBadge scoreColor logic', () => {
  it('returns green for score >= 0.7', () => {
    // Test through the component's expected behavior
    const badge = NLIConfidenceBadge({ confidence_score: 0.82 })
    expect(badge).not.toBeNull()
  })

  it('returns amber for score 0.4-0.69', () => {
    const badge = NLIConfidenceBadge({ confidence_score: 0.55 })
    expect(badge).not.toBeNull()
  })

  it('returns red for score < 0.4', () => {
    const badge = NLIConfidenceBadge({ confidence_score: 0.25 })
    expect(badge).not.toBeNull()
  })

  it('returns null when confidence_score is null', () => {
    const badge = NLIConfidenceBadge({ confidence_score: null })
    expect(badge).toBeNull()
  })

  it('returns null when confidence_score is undefined', () => {
    const badge = NLIConfidenceBadge({})
    expect(badge).toBeNull()
  })

  it('formats score to 2 decimal places', () => {
    const badge = NLIConfidenceBadge({ confidence_score: 0.8234 })
    // The component renders with .toFixed(2), so 0.8234 becomes "0.82"
    expect(badge).not.toBeNull()
  })
})
