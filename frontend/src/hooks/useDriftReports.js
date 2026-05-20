import { useState, useCallback } from 'react'
import api from '../lib/api'

export function getDriftStepErrors(form, step) {
  const errs = {}
  if (step === 1) {
    if (!form.incident_date) errs.incident_date = 'Incident date is required'
    if (!form.county_fips) errs.county_fips = 'County is required'
  }
  if (step === 2) {
    if (!form.symptom_types?.length && !form.symptoms_description?.trim()) {
      errs.symptoms = 'Select at least one symptom or provide a description'
    }
  }
  return errs
}

export function useDriftReports() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const createReport = useCallback(async (data) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.post('/drift-reports', data)
      return res.data
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to submit report'
      setError(msg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const listReports = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get('/drift-reports')
      return res.data
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load reports')
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const downloadPdf = useCallback(async (reportId) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get(`/drift-reports/${reportId}/pdf`, {
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `drift_report_${reportId.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to download PDF')
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return { createReport, listReports, downloadPdf, loading, error }
}
