import { describe, expect, it } from 'vitest'
import { getDriftStepErrors } from './useDriftReports'

describe('getDriftStepErrors', () => {
  it('flags missing incident_date on step 1', () => {
    const form = { incident_date: '', county_fips: '05055', affected_crop: 'soybean' }
    const errs = getDriftStepErrors(form, 1)
    expect(errs.incident_date).toBeTruthy()
  })

  it('passes step 1 with valid date and county', () => {
    const form = { incident_date: '2024-07-14', county_fips: '05055' }
    const errs = getDriftStepErrors(form, 1)
    expect(Object.keys(errs)).toHaveLength(0)
  })

  it('flags missing symptoms_description on step 2', () => {
    const form = { symptom_types: [], symptoms_description: '' }
    const errs = getDriftStepErrors(form, 2)
    expect(errs.symptoms).toBeTruthy()
  })

  it('passes step 2 when symptom_types has entries', () => {
    const form = { symptom_types: ['Cupping'], symptoms_description: '' }
    const errs = getDriftStepErrors(form, 2)
    expect(Object.keys(errs)).toHaveLength(0)
  })
})
