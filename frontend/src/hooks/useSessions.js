import api from '../lib/api'

export function useSessions() {
  async function listSessions() {
    const res = await api.get('/sessions')
    return res.data.sessions // SessionResponse[]
  }

  async function createSession(preview = '') {
    const res = await api.post('/sessions', { preview: String(preview).slice(0, 100) })
    return res.data // { id, preview, message_count, created_at, last_message_at }
  }

  // Returns { messages, sessionHistory } in the format ChatPage expects.
  // messages: { id, role, type, content }[]  (content is parsed for advisory)
  // sessionHistory: { role, content }[]  (last 20 raw turns for RAG context)
  async function loadSession(sessionId) {
    const res = await api.get(`/sessions/${sessionId}/messages`)
    const raw = res.data.messages

    const messages = raw.map((m) => ({
      id: m.id,
      messageId: m.id,
      role: m.role,
      type: m.content_type,
      content: m.content_type === 'advisory' ? JSON.parse(m.content) : m.content,
    }))

    const sessionHistory = raw.slice(-20).map((m) => ({
      role: m.role,
      content:
        m.content_type === 'advisory'
          ? JSON.parse(m.content).problem_summary
          : m.content,
    }))

    return { messages, sessionHistory }
  }

  return { listSessions, createSession, loadSession }
}
