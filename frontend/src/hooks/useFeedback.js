import { useState } from 'react'
import api from '../lib/api'

export function useFeedback() {
  const [submitting, setSubmitting] = useState(false)

  async function submit({ messageId, rating, comment }) {
    setSubmitting(true)
    try {
      const res = await api.post('/feedback', {
        message_id: messageId,
        rating,
        comment: comment?.trim() || null,
      })
      return { ok: true, data: res.data }
    } catch (err) {
      const status = err.response?.status
      const detail = err.response?.data?.detail || 'Could not submit feedback.'
      return { ok: false, status, detail }
    } finally {
      setSubmitting(false)
    }
  }

  return { submit, submitting }
}
