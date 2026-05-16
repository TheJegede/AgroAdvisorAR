import { useState, useCallback, useRef } from 'react'

export function parseSSEPayload(payload) {
  try {
    return { parsed: JSON.parse(payload), malformed: false }
  } catch {
    return { parsed: null, malformed: true }
  }
}

export function useSSEQuery() {
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const sendQuery = useCallback(async ({
    message,
    language,
    sessionHistory,
    sessionId,
    onResult,
    onOOS,
    onError,
  }) => {
    setStreaming(true)
    setError(null)

    const controller = new AbortController()
    abortRef.current = controller
    const token = localStorage.getItem('access_token')

    try {
      const res = await fetch('/api/v1/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message,
          language,
          session_history: sessionHistory,
          session_id: sessionId ?? null,
        }),
        signal: controller.signal,
      })

      if (!res.ok) {
        if (res.status === 401) {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
          return
        }
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Request failed: ${res.status}`)
      }

      const contentType = res.headers.get('content-type') ?? ''

      if (!contentType.includes('text/event-stream')) {
        const body = await res.json()
        onOOS(body.message, body.message_id ?? null)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          const payload = line.slice(5).trim()
          if (payload === '[DONE]') return
          const { parsed, malformed } = parseSSEPayload(payload)
          if (malformed) {
            continue
          }
          if (parsed.error) throw new Error(parsed.error)
          // Envelope shape: { advisory: AdvisoryResponse, message_id: uuid|null }
          onResult(parsed.advisory ?? parsed, parsed.message_id ?? null)
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      const msg = err.message || 'Something went wrong.'
      setError(msg)
      onError?.(msg)
    } finally {
      setStreaming(false)
    }
  }, [])

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    setStreaming(false)
  }, [])

  return { sendQuery, streaming, error, cancel }
}
