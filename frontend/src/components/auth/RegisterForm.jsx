import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useLang } from '../../contexts/LangContext'
import api from '../../lib/api'
import Alert from '../ui/Alert'
import CropCheckboxGroup from '../profile/CropCheckboxGroup'
import { COUNTY_OPTIONS } from '../../constants/counties'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const TOTAL_STEPS = 3

const INPUT_CLS = 'min-h-touch w-full rounded-xl border border-white/20 bg-white/[0.075] px-4 py-3 text-base text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] outline-none transition placeholder:text-white/40 focus:border-emerald-200/70 focus:bg-white/[0.11] focus:ring-2 focus:ring-emerald-200/25 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'
const INPUT_ERR_CLS = 'border-red-400/60 focus:border-red-400/80 focus:ring-red-300/25'
const BTN_PRIMARY_CLS = 'flex-1 inline-flex items-center justify-center gap-2 min-h-touch rounded-xl bg-gradient-to-r from-emerald-400 via-lime-300 to-harvest px-5 py-3 font-bold text-[#092014] shadow-[0_16px_36px_rgba(45,106,79,0.34),inset_0_1px_0_rgba(255,255,255,0.42)] transition hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-emerald-100/70 disabled:cursor-not-allowed disabled:opacity-60 dark:border-2 dark:border-hc-border dark:bg-hc-accent dark:bg-none dark:text-hc-accent-fg'
const BTN_GHOST_CLS = 'flex-1 min-h-touch rounded-xl border border-white/25 bg-white/[0.075] px-4 py-3 font-semibold text-white/80 transition hover:bg-white/[0.12] focus:outline-none focus:ring-2 focus:ring-white/20 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'

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
                    ? 'bg-emerald-400 text-[#092014] border-emerald-400 dark:bg-hc-accent dark:text-hc-accent-fg dark:border-hc-border'
                    : isDone
                      ? 'bg-emerald-400/70 text-[#092014] border-emerald-400/70 dark:bg-hc-fg dark:text-hc-bg dark:border-hc-border'
                      : 'bg-white/10 text-white/50 border-white/25 dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border',
                ].join(' ')}
              >
                {isDone ? '✓' : n}
              </span>
              <span
                className={[
                  'text-xs mt-1 font-medium',
                  isCurrent
                    ? 'text-white dark:text-hc-fg'
                    : isDone
                      ? 'text-emerald-300 dark:text-hc-fg'
                      : 'text-white/50 dark:text-hc-fg',
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
                  isDone ? 'bg-emerald-400/70 dark:bg-hc-fg' : 'bg-white/20 dark:bg-hc-border',
                ].join(' ')}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function GlassInput({ label, id, error, type = 'text', ...rest }) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={id} className="text-sm font-medium text-white/80 dark:text-hc-fg">
          {label}
        </label>
      )}
      <input
        id={id}
        type={type}
        className={`${INPUT_CLS} ${error ? INPUT_ERR_CLS : ''}`}
        {...rest}
      />
      {error && <p className="text-sm text-red-300 dark:text-hc-danger font-bold">{error}</p>}
    </div>
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
    const stepErrors = { 1: getStepErrors(1), 2: getStepErrors(2) }
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

      <p className="text-sm text-white/70 dark:text-hc-fg" aria-live="polite">
        {t.wizardStep} {step} {t.wizardOf} {TOTAL_STEPS} —{' '}
        <span className="font-semibold text-white dark:text-hc-fg">{headings[step - 1]}</span>
      </p>

      {error && <Alert variant="error" dismissible>{error}</Alert>}
      {info && <Alert variant="success">{info}</Alert>}

      {step === 1 && (
        <>
          <GlassInput
            id="full_name"
            label={t.fullName}
            value={form.full_name}
            onChange={set('full_name')}
            error={fieldErrors.full_name}
            required
            autoComplete="name"
            placeholder={t.fullName}
          />
          <GlassInput
            id="email"
            label={t.email}
            type="email"
            value={form.email}
            onChange={set('email')}
            error={fieldErrors.email}
            required
            autoComplete="email"
            placeholder={t.email}
          />
          <GlassInput
            id="password"
            label={t.password}
            type="password"
            value={form.password}
            onChange={set('password')}
            error={fieldErrors.password}
            required
            autoComplete="new-password"
            placeholder={t.password}
          />
        </>
      )}

      {step === 2 && (
        <>
          <div className="flex flex-col gap-1">
            <label htmlFor="county_fips" className="text-sm font-medium text-white/80 dark:text-hc-fg">
              {t.county}
            </label>
            <select
              id="county_fips"
              value={form.county_fips}
              onChange={set('county_fips')}
              className={`${INPUT_CLS} [&>option]:bg-slate-900 [&>option]:text-white ${fieldErrors.county_fips ? INPUT_ERR_CLS : ''}`}
            >
              <option value="">-- Select --</option>
              {COUNTY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            {fieldErrors.county_fips && (
              <p className="text-sm text-red-300 dark:text-hc-danger font-bold">{fieldErrors.county_fips}</p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <p className="text-sm font-medium text-white/80 dark:text-hc-fg">{t.primaryCrops}</p>
            <div className="[&_span]:!text-white/90 [&_span]:dark:!text-hc-fg">
              <CropCheckboxGroup
                value={form.primary_crops}
                onChange={(crops) => setForm((f) => ({ ...f, primary_crops: crops }))}
              />
            </div>
            {fieldErrors.primary_crops && (
              <p className="text-sm text-red-300 dark:text-hc-danger font-bold">{fieldErrors.primary_crops}</p>
            )}
          </div>
        </>
      )}

      {step === 3 && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-white/80 dark:text-hc-fg">{t.languagePref}</p>
          <div className="flex gap-4">
            {['en', 'es'].map((l) => (
              <label key={l} className="flex items-center gap-2 cursor-pointer min-h-touch">
                <input
                  type="radio"
                  name="language"
                  value={l}
                  checked={form.language === l}
                  onChange={() => setForm((f) => ({ ...f, language: l }))}
                  className="accent-emerald-400 dark:accent-hc-fg w-5 h-5"
                />
                <span className="text-base text-white/90 dark:text-hc-fg">
                  {l === 'en' ? 'English' : 'Español'}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 mt-2">
        {step > 1 && (
          <button type="button" onClick={handleBack} className={BTN_GHOST_CLS}>
            {t.back}
          </button>
        )}
        {step < TOTAL_STEPS && (
          <button type="button" onClick={handleNext} className={BTN_PRIMARY_CLS}>
            {t.next}
          </button>
        )}
        {step === TOTAL_STEPS && (
          <button type="submit" disabled={loading} className={BTN_PRIMARY_CLS}>
            {loading && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#092014]/30 border-t-[#092014]" aria-hidden="true" />
            )}
            {t.register}
          </button>
        )}
      </div>

      <p className="text-center text-sm text-white/70 dark:text-hc-fg">
        {t.alreadyHaveAccount}{' '}
        <Link to="/login" className="text-emerald-300 font-bold hover:text-emerald-100 hover:underline dark:text-hc-accent">
          {t.login}
        </Link>
      </p>
    </form>
  )
}
