import { describe, expect, it } from 'vitest'
import { getRegistrationStepErrors } from './RegisterForm'

const t = {
  errNameRequired: 'Name required',
  errEmailInvalid: 'Email invalid',
  errPasswordShort: 'Password short',
  errCountyRequired: 'County required',
  errCropRequired: 'Crop required',
}

describe('getRegistrationStepErrors', () => {
  it('keeps errors from both registration steps mergeable', () => {
    const form = {
      full_name: '',
      email: 'bad',
      password: 'short',
      county_fips: '',
      primary_crops: [],
    }

    const merged = {
      ...getRegistrationStepErrors(form, t, 1),
      ...getRegistrationStepErrors(form, t, 2),
    }

    expect(merged).toEqual({
      full_name: 'Name required',
      email: 'Email invalid',
      password: 'Password short',
      county_fips: 'County required',
      primary_crops: 'Crop required',
    })
  })
})
