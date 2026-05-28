// frontend/src/components/AlertBanner.test.jsx
import { describe, expect, it } from 'vitest'
import { selectMessage } from './AlertBanner'

describe('selectMessage', () => {
  it('returns message directly (already language-selected by API)', () => {
    const alert = { message: 'RWW EN' }
    expect(selectMessage(alert)).toBe('RWW EN')
  })

  it('returns empty string for null message', () => {
    expect(selectMessage({ message: null })).toBe('')
  })
})
