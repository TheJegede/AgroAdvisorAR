import { describe, expect, it } from 'vitest'
import { parseSSEPayload } from './useSSEQuery'

describe('parseSSEPayload', () => {
  it('parses streamed error envelopes instead of treating them as keepalives', () => {
    const { parsed, malformed } = parseSSEPayload('{"error":"RAG failed"}')

    expect(malformed).toBe(false)
    expect(parsed.error).toBe('RAG failed')
  })

  it('marks malformed keepalive payloads as malformed', () => {
    const { parsed, malformed } = parseSSEPayload(': keepalive')

    expect(malformed).toBe(true)
    expect(parsed).toBeNull()
  })
})
