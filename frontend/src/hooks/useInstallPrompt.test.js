import { describe, expect, it } from 'vitest'
import { installReducer, INITIAL_INSTALL_STATE } from './useInstallPrompt'

describe('installReducer', () => {
  it('captures a deferred prompt and becomes installable', () => {
    const evt = { prompt: () => {} }
    const next = installReducer(INITIAL_INSTALL_STATE, { type: 'captured', event: evt })
    expect(next.installable).toBe(true)
    expect(next.deferred).toBe(evt)
  })

  it('clears state after install', () => {
    const evt = { prompt: () => {} }
    const captured = installReducer(INITIAL_INSTALL_STATE, { type: 'captured', event: evt })
    const installed = installReducer(captured, { type: 'installed' })
    expect(installed.installable).toBe(false)
    expect(installed.deferred).toBeNull()
  })

  it('dismiss hides the affordance without losing installability flag semantics', () => {
    const evt = { prompt: () => {} }
    const captured = installReducer(INITIAL_INSTALL_STATE, { type: 'captured', event: evt })
    const dismissed = installReducer(captured, { type: 'dismissed' })
    expect(dismissed.dismissed).toBe(true)
  })
})
