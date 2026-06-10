import { useState, useCallback, useRef } from 'react'
import {
  clearAuthStorage,
  getAccessToken,
  redirectToLogin,
  refreshAuthToken,
} from '../lib/authTokens'

export function parseSSEPayload(payload) {
  try {
    return { parsed: JSON.parse(payload), malformed: false }
  } catch {
    return { parsed: null, malformed: true }
  }
}

// Returned to onError when a stream ends without delivering an advisory/oos/error.
// ChatPage maps this code to a friendly, localized message.
export const STREAM_EMPTY_CODE = 'stream_empty'

// Reads the SSE body. Returns true if at least one advisory was delivered via
// onResult, false if the stream ended (reader done or [DONE]) with nothing.
// Throws Error(message) on a streamed {error} frame. Comment lines (": ...")
// and malformed payloads are skipped.
export async function consumeSSEStream(reader, { onResult, onCategory }) {
  const decoder = new TextDecoder()
  let buffer = ''
  let delivered = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()

    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (payload === '[DONE]') return delivered
      const { parsed, malformed } = parseSSEPayload(payload)
      if (malformed) continue
      if (parsed.error) throw new Error(parsed.error)
      if (parsed.category) onCategory?.(parsed.category)
      onResult(parsed.advisory ?? parsed, parsed.message_id ?? null, parsed.category ?? null)
      delivered = true
    }
  }

  return delivered
}

// Abort any in-flight stream before starting a new one, then store the new
// controller. A double-submit (chip + Enter) would otherwise run two streams,
// both calling onResult (duplicate cards / out-of-order history) with only the
// latest cancelable.
export function beginRequest(abortRef) {
  abortRef.current?.abort()
  const controller = new AbortController()
  abortRef.current = controller
  return controller
}

function queryHeaders(token) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

export async function fetchQueryWithAuth({ payload, signal }) {
  const runFetch = (token) => fetch('/api/v1/query', {
    method: 'POST',
    headers: queryHeaders(token),
    body: JSON.stringify(payload),
    signal,
  })

  let res = await runFetch(getAccessToken())
  if (res.status !== 401) return res

  try {
    const refreshedToken = await refreshAuthToken()
    res = await runFetch(refreshedToken)
  } catch {
    clearAuthStorage()
    redirectToLogin()
    return null
  }

  if (res.status === 401) {
    clearAuthStorage()
    redirectToLogin()
    return null
  }

  return res
}

export function useSSEQuery() {
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState(null)
  const [retryable, setRetryable] = useState(false)
  const abortRef = useRef(null)
  const lastQueryRef = useRef(null)

  const sendQuery = useCallback(async ({
    message,
    language,
    sessionHistory,
    sessionId,
    lastCategory,
    onResult,
    onOOS,
    onError,
    onCategory,
  }) => {
    setStreaming(true)
    setError(null)
    setRetryable(false)
    lastQueryRef.current = { message, language, sessionHistory, sessionId, lastCategory, onResult, onOOS, onError, onCategory }

    const controller = beginRequest(abortRef)

    try {
      const res = await fetchQueryWithAuth({
        payload: {
          message,
          language,
          session_history: sessionHistory,
          session_id: sessionId ?? null,
          last_category: lastCategory ?? null,
        },
        signal: controller.signal,
      })

      if (!res) return

      if (!res.ok) {
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
          // Envelope shape: { advisory: AdvisoryResponse, message_id: uuid|null, category: string }
          if (parsed.category) onCategory?.(parsed.category)
          onResult(parsed.advisory ?? parsed, parsed.message_id ?? null, parsed.category ?? null)
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      const msg = err.message || 'Something went wrong.'
      setError(msg)
      setRetryable(true)
      onError?.(msg)
    } finally {
      setStreaming(false)
    }
  }, [])

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    setStreaming(false)
  }, [])

  const retry = useCallback(() => {
    if (lastQueryRef.current) sendQuery(lastQueryRef.current)
  }, [sendQuery])

  return { sendQuery, streaming, error, cancel, retry, retryable }
}
