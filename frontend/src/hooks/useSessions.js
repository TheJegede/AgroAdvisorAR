import { useCallback } from 'react'
import api from '../lib/api'

export function parseAdvisory(content) {
  try {
    return JSON.parse(content)
  } catch {
    return {
      problem_summary: 'This saved advisory could not be loaded.',
      likely_causes: [],
      recommended_actions: [],
      products_rates: [],
      warnings: ['The saved advisory JSON is malformed.'],
      citations: [],
      confidence: 'Low',
      confidence_explanation: 'Stored advisory content was not valid JSON.',
      language: 'en',
      context_meta: {
        soil_data_available: false,
        weather_data_available: false,
        county_fips: '',
      },
    }
  }
}

export function useSessions() {
  const listSessions = useCallback(async () => {
    const res = await api.get('/sessions')
    return res.data.sessions // SessionResponse[]
  }, [])

  const createSession = useCallback(async (preview = '') => {
    const res = await api.post('/sessions', { preview: String(preview).slice(0, 100) })
    return res.data // { id, preview, message_count, created_at, last_message_at }
  }, [])

  // Returns { messages, sessionHistory } in the format ChatPage expects.
  // messages: { id, role, type, content }[]  (content is parsed for advisory)
  // sessionHistory: { role, content }[]  (last 20 raw turns for RAG context)
  const loadSession = useCallback(async (sessionId) => {
    const res = await api.get(`/sessions/${sessionId}/messages`)
    const raw = res.data.messages

    const parsedAdvisories = new Map()
    const getParsedAdvisory = (message) => {
      if (!parsedAdvisories.has(message.id)) {
        parsedAdvisories.set(message.id, parseAdvisory(message.content))
      }
      return parsedAdvisories.get(message.id)
    }

    const messages = raw.map((m) => ({
      id: m.id,
      messageId: m.id,
      role: m.role,
      type: m.content_type,
      content: m.content_type === 'advisory' ? getParsedAdvisory(m) : m.content,
    }))

    const sessionHistory = raw.slice(-20).map((m) => ({
      role: m.role,
      content:
        m.content_type === 'advisory'
          ? getParsedAdvisory(m).problem_summary
          : m.content,
    }))

    return { messages, sessionHistory }
  }, [])

  const deleteSession = useCallback(async (sessionId) => {
    await api.delete(`/sessions/${sessionId}`)
  }, [])

  return { listSessions, createSession, loadSession, deleteSession }
}
