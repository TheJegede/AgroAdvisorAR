import { describe, expect, it, vi } from 'vitest'
import QueryProgress from './QueryProgress'

vi.mock('../../contexts/LangContext', () => ({
  useLang: () => ({
    lang: 'en',
    t: {
      progressSearching: 'Searching extension sources…',
      progressFoundSources: 'Found {n} sources',
      progressWriting: 'Writing advisory…',
      progressVerifying: 'Verifying against sources…',
    },
  }),
}))

describe('QueryProgress', () => {
  it('renders without error when stage is null', () => {
    const el = QueryProgress({ stage: null })
    expect(el).not.toBeNull()
  })

  it('renders with sources_found stage', () => {
    const el = QueryProgress({ stage: { stage: 'sources_found', count: 2, titles: ['Rice MP154', 'Sheath Blight'] } })
    expect(el).not.toBeNull()
  })

  it('renders with writing stage', () => {
    const el = QueryProgress({ stage: { stage: 'writing' } })
    expect(el).not.toBeNull()
  })
})
