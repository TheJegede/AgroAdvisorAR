import { describe, expect, it } from 'vitest'
import { parseSSEPayload, beginRequest } from './useSSEQuery'

describe('beginRequest', () => {
  it('aborts the previous controller before assigning a new one', () => {
    const ref = { current: null }
    const first = beginRequest(ref)
    const second = beginRequest(ref)

    expect(first.signal.aborted).toBe(true)
    expect(second.signal.aborted).toBe(false)
    expect(ref.current).toBe(second)
  })

  it('is a no-op on the first request (no prior controller)', () => {
    const ref = { current: null }
    const controller = beginRequest(ref)
    expect(controller.signal.aborted).toBe(false)
    expect(ref.current).toBe(controller)
  })
})

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
