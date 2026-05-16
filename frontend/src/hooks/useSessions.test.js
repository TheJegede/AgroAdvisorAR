import { describe, expect, it } from 'vitest'
import { parseAdvisory } from './useSessions'

describe('parseAdvisory', () => {
  it('returns a fallback advisory for malformed stored JSON', () => {
    const advisory = parseAdvisory('{bad json')

    expect(advisory.problem_summary).toBe('This saved advisory could not be loaded.')
    expect(advisory.warnings).toContain('The saved advisory JSON is malformed.')
  })
})
