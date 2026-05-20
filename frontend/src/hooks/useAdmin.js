import { useState, useEffect, useCallback } from 'react'
import api from '../lib/api'

export function useAdminMetrics() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(() => {
    setLoading(true)
    api.get('/admin/metrics')
      .then(({ data }) => setMetrics(data))
      .catch((err) => setError(err.response?.data?.detail || 'Failed to load metrics'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return { metrics, loading, error, refresh }
}


export function useEvalQueue() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('flagged')
  const [offset, setOffset] = useState(0)

  const load = useCallback(async (opts = {}) => {
    setLoading(true)
    setError(null)
    const f = opts.filter ?? filter
    const o = opts.offset ?? offset
    try {
      const { data } = await api.get('/admin/eval/queue', {
        params: { filter: f, limit: 20, offset: o },
      })
      setItems(data.items)
      setFilter(f)
      setOffset(o)
      return data
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load queue')
      return null
    } finally {
      setLoading(false)
    }
  }, [filter, offset])

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function submitScore({ messageId, accuracyScore, correction }) {
    try {
      await api.post('/admin/eval/score', {
        message_id: messageId,
        accuracy_score: accuracyScore,
        correction: correction?.trim() || null,
      })
      // Remove from current view (next load will refetch)
      setItems((prev) => prev.filter((m) => m.id !== messageId))
      return { ok: true }
    } catch (err) {
      return { ok: false, detail: err.response?.data?.detail || 'Score submit failed' }
    }
  }

  return { items, loading, error, filter, offset, load, submitScore }
}


export function useDriftReportAdmin() {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async ({ dateFrom, dateTo } = {}) => {
    setLoading(true)
    setError(null)
    try {
      const params = {}
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      const { data } = await api.get('/admin/drift-reports', { params })
      setReports(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load drift reports')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return { reports, loading, error, refresh }
}
