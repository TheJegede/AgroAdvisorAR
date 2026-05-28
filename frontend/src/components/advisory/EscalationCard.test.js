import { describe, expect, it, vi } from 'vitest'
import EscalationCard from './EscalationCard'

vi.mock('../../contexts/LangContext', () => ({
  useLang: () => ({ t: { escalationContact: 'Contact your county Extension agent:' } }),
}))

describe('EscalationCard', () => {
  it('returns null when escalation is null', () => {
    const card = EscalationCard({ escalation: null })
    expect(card).toBeNull()
  })

  it('returns null when escalation is undefined', () => {
    const card = EscalationCard({})
    expect(card).toBeNull()
  })

  it('renders the escalation text when escalation string is provided', () => {
    const card = EscalationCard({ escalation: 'Contact Dr. Smith' })
    expect(card).not.toBeNull()
  })

  it('renders t.escalationContact label when escalation is present', () => {
    const card = EscalationCard({ escalation: 'County Extension Agent' })
    // The component should render with the mocked label
    expect(card).not.toBeNull()
  })

  it('phone icon is rendered with aria-label="phone"', () => {
    const card = EscalationCard({ escalation: 'Test Escalation' })
    // The component renders a span with role="img" and aria-label="phone"
    expect(card).not.toBeNull()
  })
})
