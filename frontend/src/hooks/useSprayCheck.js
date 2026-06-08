import { useState, useCallback } from 'react'
import api from '../lib/api'

// Per-step validation, mirrors getDriftStepErrors. Exported standalone so the
// step gating is unit-testable without mounting the wizard.
export function getSprayStepErrors(form, step) {
  const errs = {}
  if (step === 1) {
    if (!form.product) errs.product = 'Select the product you plan to apply'
    if (!form.license_attested) errs.license = 'You must attest your applicator license'
  }
  if (step === 2) {
    // 0 is a valid coordinate — check for null/undefined, not falsiness.
    if (form.lat == null || form.lon == null) {
      errs.pin = 'Drop a pin on your field to pull live conditions'
    }
  }
  return errs
}

export function useSprayCheck() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const runCheck = useCallback(async ({ lat, lon, product, at, attestation }) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.post('/dicamba/check', {
        lat,
        lon,
        product,
        // Default to now if the caller does not pin a time.
        at: at || new Date().toISOString(),
        attestation: attestation || {},
      })
      return res.data
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to run the spray check'
      setError(msg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return { runCheck, loading, error }
}
