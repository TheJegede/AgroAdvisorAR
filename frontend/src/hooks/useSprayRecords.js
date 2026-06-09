import { useState, useEffect, useCallback } from 'react'
import api from '../lib/api'

// Standalone fetch so the network path is unit-testable without rendering the
// hook (the project has no DOM test environment — see useDriftReports.test.js).
export async function fetchSprayRecords() {
  const res = await api.get('/dicamba/records')
  return res.data
}

// Fetch the record PDF through the axios client (responseType blob) so the
// Bearer token is attached. A plain <a href> nav sent no Authorization header
// and the backend returned 401 "Not authenticated". Standalone for unit tests
// (no DOM env — see fetchSprayRecords note above).
export async function fetchSprayPdfBlob(recordId) {
  const res = await api.get(`/dicamba/record/${recordId}/pdf`, {
    responseType: 'blob',
  })
  return res.data
}

// Trigger a browser download of the authed PDF blob. Mirrors
// useDriftReports.downloadPdf (the working drift-report path).
export async function downloadSprayPdf(recordId) {
  const blob = await fetchSprayPdfBlob(recordId)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `spray_record_${recordId.slice(0, 8)}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
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
