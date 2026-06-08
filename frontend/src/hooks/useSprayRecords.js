import { useState, useEffect, useCallback } from 'react'
import api from '../lib/api'

// Standalone fetch so the network path is unit-testable without rendering the
// hook (the project has no DOM test environment — see useDriftReports.test.js).
export async function fetchSprayRecords() {
  const res = await api.get('/dicamba/records')
  return res.data
}

export function useSprayRecords() {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchRecords = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchSprayRecords()
      setRecords(data)
      return data
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load records')
      return []
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchRecords() }, [fetchRecords])

  return { records, loading, error, fetchRecords }
}
