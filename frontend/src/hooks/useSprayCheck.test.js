import { describe, expect, it } from 'vitest'
import { getSprayStepErrors } from './useSprayCheck'

describe('getSprayStepErrors', () => {
  it('flags missing product on step 1', () => {
    const form = { product: '', license_attested: true }
    const errs = getSprayStepErrors(form, 1)
    expect(errs.product).toBeTruthy()
  })

  it('flags un-attested license on step 1', () => {
    const form = { product: 'engenia', license_attested: false }
    const errs = getSprayStepErrors(form, 1)
    expect(errs.license).toBeTruthy()
  })

  it('passes step 1 with product and license attested', () => {
    const form = { product: 'engenia', license_attested: true }
    const errs = getSprayStepErrors(form, 1)
    expect(Object.keys(errs)).toHaveLength(0)
  })

  it('flags missing pin on step 2', () => {
    const form = { lat: null, lon: null }
    const errs = getSprayStepErrors(form, 2)
    expect(errs.pin).toBeTruthy()
  })

  it('passes step 2 once a pin is placed', () => {
    const form = { lat: 34.7, lon: -91.2 }
    const errs = getSprayStepErrors(form, 2)
    expect(Object.keys(errs)).toHaveLength(0)
  })

  it('treats lat/lon of 0 as a valid pin (not missing)', () => {
    const form = { lat: 0, lon: 0 }
    const errs = getSprayStepErrors(form, 2)
    expect(errs.pin).toBeFalsy()
  })

  it('imposes no required fields on step 3', () => {
    const errs = getSprayStepErrors({}, 3)
    expect(Object.keys(errs)).toHaveLength(0)
  })
})
