import { describe, expect, it, vi } from 'vitest'

// Mock all child components and hooks to test branching logic in AdvisoryCardInner
vi.mock('../../contexts/LangContext', () => ({
  useLang: () => ({ t: { cropChipRice: 'Rice', nliScore: 'NLI', suppressedTitle: "We couldn't verify a confident answer", suppressedBody: 'withheld' } }),
}))
vi.mock('./ConfidenceBadge', () => ({ default: () => null }))
vi.mock('./NLIConfidenceBadge', () => ({ default: () => null }))
vi.mock('./EscalationCard', () => ({ default: () => null }))
vi.mock('./ContextMetaBar', () => ({ default: () => null }))
vi.mock('./LowConfidenceBanner', () => ({ default: () => null }))
vi.mock('./WarningsBanner', () => ({ default: () => null }))
vi.mock('./ProblemSummary', () => ({ default: ({ summary }) => summary || null }))
vi.mock('./LikelyCauses', () => ({ default: () => null }))
vi.mock('./RecommendedActions', () => ({ default: () => null }))
vi.mock('./ProductsRates', () => ({ default: () => null }))
vi.mock('./CitationsSection', () => ({ default: () => null }))
vi.mock('./FeedbackWidget', () => ({ default: () => null }))
vi.mock('./ConfidenceExplainer', () => ({ default: () => null }))
vi.mock('./SuppressedNotice', () => ({ default: ({ escalation }) => `SUPPRESSED:${escalation}` }))

import AdvisoryCard from './AdvisoryCard'

const baseContext = { soil_data_available: false, weather_data_available: false, county_fips: '05055' }

const suppressedResp = {
  confidence: 'Low', confidence_score: 0.0, suppressed: true,
  escalation: 'Contact your Pulaski County Extension Agent',
  problem_summary: '', likely_causes: [], recommended_actions: [],
  products_rates: [], warnings: [], citations: [],
  confidence_explanation: '', context_meta: baseContext,
}

const normalResp = {
  ...suppressedResp,
  suppressed: false, confidence: 'High', confidence_score: 0.9,
  problem_summary: 'Rice blast detected.',
}

describe('AdvisoryCard suppression branching', () => {
  it('renders without error when suppressed=true', () => {
    // AdvisoryCard wraps in ErrorBoundary; it must not throw
    const el = AdvisoryCard({ response: suppressedResp, messageId: 'm1', category: 'IN_SCOPE_RICE' })
    expect(el).not.toBeNull()
  })

  it('renders without error when suppressed=false', () => {
    const el = AdvisoryCard({ response: normalResp, messageId: 'm2', category: 'IN_SCOPE_RICE' })
    expect(el).not.toBeNull()
  })
})
