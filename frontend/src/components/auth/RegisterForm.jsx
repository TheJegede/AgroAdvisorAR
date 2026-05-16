import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useLang } from '../../contexts/LangContext'
import api from '../../lib/api'
import Input from '../ui/Input'
import Select from '../ui/Select'
import Button from '../ui/Button'
import Alert from '../ui/Alert'
import CropCheckboxGroup from '../profile/CropCheckboxGroup'
import { COUNTY_OPTIONS } from '../../constants/counties'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const TOTAL_STEPS = 3

export function getRegistrationStepErrors(form, t, step) {
  const errs = {}
  if (step === 1) {
    if (!form.full_name.trim()) errs.full_name = t.errNameRequired
    if (!EMAIL_RE.test(form.email)) errs.email = t.errEmailInvalid
    if (form.password.length < 8) errs.password = t.errPasswordShort
  }
  if (step === 2) {
    if (!form.county_fips) errs.county_fips = t.errCountyRequired
    if (!form.primary_crops.length) errs.primary_crops = t.errCropRequired
  }
  return errs
}

function StepIndicator({ step, titles }) {
  return (
    <ol className="flex items-center justify-between mb-6" aria-label="registration steps">
      {titles.map((title, i) => {
        const n = i + 1
        const isCurrent = n === step
        const isDone = n < step
        return (
          <li key={n} className="flex-1 flex items-center">
            <div className="flex flex-col items-center flex-1">
              <span
                aria-current={isCurrent ? 'step' : undefined}
                className={[
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-colors',
                  isCurrent
                    ? 'bg-field text-white border-field dark:bg-hc-accent dark:text-hc-accent-fg dark:border-hc-border'
                    : isDone
                      ? 'bg-field text-white border-field dark:bg-hc-fg dark:text-hc-bg dark:border-hc-border'
                      : 'bg-white text-gray-600 border-gray-300 dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border',
                ].join(' ')}
              >
                {isDone ? '✓' : n}
              </span>
              <span
                className={[
                  'text-xs mt-1 font-medium',
                  isCurrent
                    ? 'text-charcoal dark:text-hc-fg'
                    : isDone
                      ? 'text-field dark:text-hc-fg'
                      : 'text-gray-600 dark:text-hc-fg',
                ].join(' ')}
              >
                {title}
              </span>
            </div>
            {n < titles.length && (
              <span
                aria-hidden
                className={[
                  'h-0.5 flex-1 -mt-4',
                  isDone
                    ? 'bg-field dark:bg-hc-fg'
                    : 'bg-gray-300 dark:bg-hc-border',
                ].join(' ')}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}

export default function RegisterForm() {
  const { login } = useAuth()
  const { t, setLang } = useLang()
  const navigate = useNavigate()

  const [step, setStep] = useState(1)
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    county_fips: '',
    primary_crops: [],
    language: 'en',
  })
  const [fieldErrors, setFieldErrors] = useState({})
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)

  function set(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target ? e.target.value : e }))
  }

  function getStepErrors(n) {
    return getRegistrationStepErrors(form, t, n)
  }

  function validateStep(n) {
    const errs = getStepErrors(n)
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  function handleNext() {
    if (!validateStep(step)) return
    setError('')
    setStep((s) => Math.min(s + 1, TOTAL_STEPS))
  }

  function handleBack() {
    setError('')
    setFieldErrors({})
    setStep((s) => Math.max(s - 1, 1))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const stepErrors = {
      1: getStepErrors(1),
      2: getStepErrors(2),
    }
    const mergedErrors = { ...stepErrors[1], ...stepErrors[2] }
    if (Object.keys(mergedErrors).length > 0) {
      setFieldErrors(mergedErrors)
      setStep(Object.keys(stepErrors[1]).length > 0 ? 1 : 2)
      return
    }
    setError('')
    setInfo('')
    setLoading(true)
    try {
      const { data } = await api.post('/auth/register', form)
      setLang(form.language)
      login(data.access_token, data.refresh_token)
      navigate('/')
    } catch (err) {
      const detail = err.response?.data?.detail || ''
      if (detail.includes('Email confirmation')) {
        setInfo(t.emailConfirmRequired)
        setTimeout(() => navigate('/login'), 3000)
      } else {
        setError(detail || t.errorGeneric)
      }
    } finally {
      setLoading(false)
    }
  }

  const titles = [t.wizardStep1Title, t.wizardStep2Title, t.wizardStep3Title]
  const headings = [t.wizardStep1Heading, t.wizardStep2Heading, t.wizardStep3Heading]

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <StepIndicator step={step} titles={titles} />

      <p className="text-sm text-gray-600 dark:text-hc-fg" aria-live="polite">
        {t.wizardStep} {step} {t.wizardOf} {TOTAL_STEPS} — <span className="font-semibold text-charcoal dark:text-hc-fg">{headings[step - 1]}</span>
      </p>

      {error && <Alert variant="error" dismissible>{error}</Alert>}
      {info && <Alert variant="success">{info}</Alert>}

      {step === 1 && (
        <>
          <Input
            id="full_name"
            label={t.fullName}
            value={form.full_name}
            onChange={set('full_name')}
            error={fieldErrors.full_name}
            required
            autoComplete="name"
          />
          <Input
            id="email"
            label={t.email}
            type="email"
            value={form.email}
            onChange={set('email')}
            error={fieldErrors.email}
            required
            autoComplete="email"
          />
          <Input
            id="password"
            label={t.password}
            type="password"
            value={form.password}
            onChange={set('password')}
            error={fieldErrors.password}
            required
            autoComplete="new-password"
          />
        </>
      )}

      {step === 2 && (
        <>
          <Select
            id="county_fips"
            label={t.county}
            options={COUNTY_OPTIONS}
            value={form.county_fips}
            onChange={set('county_fips')}
            error={fieldErrors.county_fips}
          />
          <div className="flex flex-col gap-2">
            <p className="text-sm font-medium text-charcoal dark:text-hc-fg">{t.primaryCrops}</p>
            <CropCheckboxGroup
              value={form.primary_crops}
              onChange={(crops) => setForm((f) => ({ ...f, primary_crops: crops }))}
            />
            {fieldErrors.primary_crops && (
              <p className="text-sm text-arred dark:text-hc-danger font-bold">{fieldErrors.primary_crops}</p>
            )}
          </div>
        </>
      )}

      {step === 3 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-charcoal dark:text-hc-fg">{t.languagePref}</p>
          <div className="flex gap-4">
            {['en', 'es'].map((l) => (
              <label key={l} className="flex items-center gap-2 cursor-pointer min-h-touch">
                <input
                  type="radio"
                  name="language"
                  value={l}
                  checked={form.language === l}
                  onChange={() => setForm((f) => ({ ...f, language: l }))}
                  className="accent-field dark:accent-hc-fg w-5 h-5"
                />
                <span className="text-base dark:text-hc-fg">{l === 'en' ? 'English' : 'Espanol'}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 mt-2">
        {step > 1 && (
          <Button type="button" variant="ghost" onClick={handleBack} className="flex-1">
            {t.back}
          </Button>
        )}
        {step < TOTAL_STEPS && (
          <Button type="button" onClick={handleNext} className="flex-1">
            {t.next}
          </Button>
        )}
        {step === TOTAL_STEPS && (
          <Button type="submit" loading={loading} className="flex-1">
            {t.register}
          </Button>
        )}
      </div>

      <p className="text-center text-sm text-gray-600 dark:text-hc-fg">
        {t.alreadyHaveAccount}{' '}
        <Link to="/login" className="text-field dark:text-hc-accent font-bold hover:underline">
          {t.login}
        </Link>
      </p>
    </form>
  )
}
