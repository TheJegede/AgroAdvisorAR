import { useState, useCallback } from 'react'
import api from '../lib/api'

export function buildSprayRequestPayload({ lat, lon, product, at, attestation }) {
  return {
    lat,
    lon,
    product,
    at: at || new Date().toISOString(),
    attestation: attestation || {},
  }
}

// Per-step validation, mirrors getDriftStepErrors. Exported standalone so the
// step gating is unit-testable without mounting the wizard.
export function getSprayStepErrors(form, step) {
  const errs = {}
  if (step === 1) {
    if (!form.product) errs.product = 'Select the product you plan to apply'
    if (!form.license_attested) errs.license = 'You must attest your applicator license'
  }
  if (step === 2) {
    // Step 2 is now Field & Buffers (Gate B). 0 is a valid coordinate —
    // check for null/undefined, not falsiness.
    if (form.lat == null || form.lon == null) {
      errs.pin = 'Drop a pin on your field to draw buffers and pull conditions'
    }
  }
  // Steps 3 (live conditions) and 4 (result) impose no required fields.
  return errs
}

export function useSprayCheck() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const runCheck = useCallback(async ({ lat, lon, product, at, attestation }) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.post('/dicamba/check', buildSprayRequestPayload({
        lat,
        lon,
        product,
        at,
        attestation,
      }))
      return res.data
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to run the spray check'
      setError(msg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  // Static research-station seed list for the Gate B map markers.
  const fetchStations = useCallback(async () => {
    const res = await api.get('/dicamba/stations')
    return res.data
  }, [])

  // Persist the decision as an immutable record; returns the saved row (with id).
  const saveRecord = useCallback(async ({ lat, lon, product, at, attestation }) => {
    const res = await api.post('/dicamba/record', buildSprayRequestPayload({
      lat,
      lon,
      product,
      at,
      attestation,
    }))
    return res.data
  }, [])

  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)

  const submitFeedback = useCallback(async ({ recordId, rating, comment }) => {
    setFeedbackSubmitting(true)
    try {
      const res = await api.post('/dicamba/feedback', {
        record_id: recordId,
        rating,
        comment: comment?.trim() || null,
      })
      return { ok: true, data: res.data }
    } catch (err) {
      const status = err.response?.status
      const detail = err.response?.data?.detail || 'Could not submit feedback.'
      return { ok: false, status, detail }
    } finally {
      setFeedbackSubmitting(false)
    }
  }, [])

  return {
    runCheck,
    fetchStations,
    saveRecord,
    submitFeedback,
    loading,
    error,
    feedbackSubmitting,
  }
}
