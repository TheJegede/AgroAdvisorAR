import { describe, expect, it, vi } from 'vitest'
import SuppressedNotice from './SuppressedNotice'

vi.mock('../../contexts/LangContext', () => ({
  useLang: () => ({
    t: {
      suppressedTitle: "We couldn't verify a confident answer",
      suppressedBody: 'This response was withheld because it could not be verified against our Arkansas Extension sources. Please reach out for direct guidance:',
    },
  }),
}))

describe('SuppressedNotice', () => {
  it('renders a non-null element (shows the withheld-answer card)', () => {
    const el = SuppressedNotice({ escalation: null })
    expect(el).not.toBeNull()
  })

  it('renders with escalation prop provided (no error)', () => {
    const el = SuppressedNotice({ escalation: 'Contact your Pulaski County Extension Agent' })
    expect(el).not.toBeNull()
  })

  it('renders without escalation when null', () => {
    const el = SuppressedNotice({ escalation: null })
    // Component should still render (not crash when escalation is null)
    expect(el).not.toBeNull()
  })
})
