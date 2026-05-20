import { useState, useEffect, useRef } from 'react'
import { useLang } from '../../contexts/LangContext'
import { useProfile } from '../../hooks/useProfile'
import { useDriftReports, getDriftStepErrors } from '../../hooks/useDriftReports'
import Alert from '../ui/Alert'
import { COUNTY_OPTIONS } from '../../constants/counties'

const TOTAL_STEPS = 3

const INPUT_CLS =
  'w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-base text-charcoal outline-none transition placeholder:text-gray-400 focus:border-field focus:ring-2 focus:ring-field/20 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'
const INPUT_ERR_CLS = 'border-red-400/60 focus:border-red-400/80 focus:ring-red-300/25'
const BTN_PRIMARY_CLS =
  'flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-field px-5 py-3 font-bold text-white shadow transition hover:bg-field/90 focus:outline-none focus:ring-2 focus:ring-field/50 disabled:opacity-60 dark:border-2 dark:border-hc-border dark:bg-hc-accent dark:text-hc-accent-fg'
const BTN_GHOST_CLS =
  'flex-1 rounded-xl border border-gray-200 bg-white px-4 py-3 font-semibold text-gray-600 transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'

const SYMPTOM_OPTIONS = ['Cupping', 'Strapping', 'Stunting', 'Discoloration', 'Other']

const STEP_TITLES_EN = ['Incident Basics', 'Symptoms', 'Source & Submit']
const STEP_TITLES_ES = ['Detalles del Incidente', 'Síntomas', 'Fuente y Enviar']

function StepIndicator({ step, titles }) {
  return (
    <ol className="flex items-center justify-between mb-6">
      {titles.map((title, i) => {
        const n = i + 1
        const isCurrent = n === step
        const isDone = n < step
        return (
          <li key={n} className="flex-1 flex items-center">
            <div className="flex flex-col items-center">
              <span
                aria-current={isCurrent ? 'step' : undefined}
                className={[
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-colors',
                  isCurrent
                    ? 'bg-field text-white border-field'
                    : isDone
                      ? 'bg-field/70 text-white border-field/70'
                      : 'bg-gray-100 text-gray-400 border-gray-200 dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border',
                ].join(' ')}
              >
                {isDone ? '✓' : n}
              </span>
              <span className="text-[10px] text-gray-500 mt-1 text-center leading-tight dark:text-hc-fg">
                {title}
              </span>
            </div>
            {i < titles.length - 1 && (
              <div className={`flex-1 h-px mx-1 ${isDone ? 'bg-field/50' : 'bg-gray-200'}`} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function FieldError({ msg }) {
  if (!msg) return null
  return <p className="text-xs text-red-500 mt-1">{msg}</p>
}

export default function DriftReportWizard() {
  const { lang } = useLang()
  const { profile } = useProfile()
  const { createReport, downloadPdf, loading, error } = useDriftReports()

  const [step, setStep] = useState(1)
  const [errs, setErrs] = useState({})
  const [submitted, setSubmitted] = useState(null)
  const profileCountySynced = useRef(false)

  const [form, setForm] = useState({
    incident_date: '',
    county_fips: profile?.county_fips || '',
    affected_crop: '',
    affected_acres: '',
    symptom_types: [],
    symptoms_description: '',
    neighboring_applicator: '',
    photos_field: false,
    photos_gps: false,
    photos_records: false,
    aspb_submitted: false,
  })

  useEffect(() => {
    if (profile?.county_fips && !profileCountySynced.current) {
      profileCountySynced.current = true
      set('county_fips', profile.county_fips)
    }
  }, [profile?.county_fips])

  const stepTitles = lang === 'es' ? STEP_TITLES_ES : STEP_TITLES_EN

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  function toggleSymptom(s) {
    setForm((f) => ({
      ...f,
      symptom_types: f.symptom_types.includes(s)
        ? f.symptom_types.filter((x) => x !== s)
        : [...f.symptom_types, s],
    }))
  }

  function handleNext() {
    const stepErrs = getDriftStepErrors(form, step)
    if (Object.keys(stepErrs).length > 0) {
      setErrs(stepErrs)
      return
    }
    setErrs({})
    setStep((s) => s + 1)
  }

  async function handleSubmit() {
    const stepErrs = getDriftStepErrors(form, 3)
    if (Object.keys(stepErrs).length > 0) {
      setErrs(stepErrs)
      return
    }
    setErrs({})

    const symptomsText = [
      form.symptom_types.join(', '),
      form.symptoms_description.trim(),
    ]
      .filter(Boolean)
      .join(': ')

    try {
      const report = await createReport({
        incident_date: form.incident_date,
        county_fips: form.county_fips || profile?.county_fips,
        affected_crop: form.affected_crop || null,
        affected_acres: form.affected_acres ? parseFloat(form.affected_acres) : null,
        symptoms_description: symptomsText || null,
        neighboring_applicator: form.neighboring_applicator.trim() || null,
        photos_attached: form.photos_field || form.photos_gps || form.photos_records,
        aspb_submitted: form.aspb_submitted,
      })
      setSubmitted(report)
    } catch {
      // error shown via hook's error state
    }
  }

  if (submitted) {
    return (
      <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm dark:bg-hc-surface dark:border-hc-border">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-field/10 flex items-center justify-center text-field text-xl">✓</div>
          <div>
            <p className="font-semibold text-charcoal dark:text-hc-fg">
              {lang === 'es' ? 'Reporte enviado' : 'Report submitted'}
            </p>
            <p className="text-xs text-gray-500 dark:text-hc-fg">
              {lang === 'es' ? 'ID de reporte:' : 'Report ID:'} {submitted.id?.slice(0, 8)}
            </p>
          </div>
        </div>

        {submitted.wind_speed_mph != null && (
          <div className="bg-gray-50 rounded-xl p-4 mb-4 text-sm dark:bg-hc-bg">
            <p className="font-semibold text-charcoal dark:text-hc-fg mb-2">
              {lang === 'es' ? 'Condiciones meteorológicas auto-llenadas:' : 'Auto-filled weather conditions:'}
            </p>
            <p className="text-gray-600 dark:text-hc-fg">
              Wind: {submitted.wind_speed_mph} mph {submitted.wind_direction} · Temp: {submitted.temp_at_time_f}°F
            </p>
          </div>
        )}

        <button
          onClick={() => downloadPdf(submitted.id)}
          className={BTN_PRIMARY_CLS + ' w-full mt-2'}
        >
          {lang === 'es' ? 'Descargar PDF de queja ASPB' : 'Download ASPB Complaint PDF'}
        </button>
        <button
          onClick={() => { setSubmitted(null); setStep(1); setForm(f => ({ ...f, incident_date: '', affected_crop: '', affected_acres: '', symptom_types: [], symptoms_description: '', neighboring_applicator: '', photos_field: false, photos_gps: false, photos_records: false, aspb_submitted: false })) }}
          className={BTN_GHOST_CLS + ' w-full mt-2'}
        >
          {lang === 'es' ? 'Nuevo reporte' : 'File another report'}
        </button>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm dark:bg-hc-surface dark:border-hc-border">
      <h1 className="text-lg font-bold text-charcoal dark:text-hc-fg mb-1">
        {lang === 'es' ? 'Reporte de Deriva de Dicamba' : 'Dicamba Drift Report'}
      </h1>
      <p className="text-sm text-gray-500 dark:text-hc-fg mb-6">
        {lang === 'es'
          ? 'Documente un incidente de deriva y genere una queja para el ASPB.'
          : 'Document a drift incident and generate an ASPB complaint package.'}
      </p>

      <StepIndicator step={step} titles={stepTitles} />

      {error && <Alert variant="error" className="mb-4">{error}</Alert>}

      {/* Step 1 */}
      {step === 1 && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Fecha del incidente *' : 'Incident date *'}
            </label>
            <input
              type="date"
              max={new Date().toISOString().split('T')[0]}
              value={form.incident_date}
              onChange={(e) => set('incident_date', e.target.value)}
              className={`${INPUT_CLS} ${errs.incident_date ? INPUT_ERR_CLS : ''}`}
            />
            <FieldError msg={errs.incident_date} />
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Cultivo afectado' : 'Affected crop'}
            </label>
            <select
              value={form.affected_crop}
              onChange={(e) => set('affected_crop', e.target.value)}
              className={INPUT_CLS}
            >
              <option value="">{lang === 'es' ? 'Seleccionar...' : 'Select...'}</option>
              <option value="rice">{lang === 'es' ? 'Arroz' : 'Rice'}</option>
              <option value="soybean">{lang === 'es' ? 'Soja' : 'Soybean'}</option>
              <option value="other">{lang === 'es' ? 'Otro' : 'Other'}</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Acres estimados' : 'Estimated acres'}
            </label>
            <input
              type="number"
              min="0"
              step="0.1"
              value={form.affected_acres}
              onChange={(e) => set('affected_acres', e.target.value)}
              placeholder="0.0"
              className={INPUT_CLS}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Condado *' : 'County *'}
            </label>
            <select
              value={form.county_fips}
              onChange={(e) => set('county_fips', e.target.value)}
              className={`${INPUT_CLS} ${errs.county_fips ? INPUT_ERR_CLS : ''}`}
            >
              <option value="">{lang === 'es' ? 'Seleccionar condado...' : 'Select county...'}</option>
              {COUNTY_OPTIONS.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
            <FieldError msg={errs.county_fips} />
          </div>
        </div>
      )}

      {/* Step 2 */}
      {step === 2 && (
        <div className="space-y-4">
          <div>
            <p className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-2">
              {lang === 'es' ? 'Tipo de síntomas observados' : 'Observed symptom types'}
            </p>
            <div className="grid grid-cols-2 gap-2">
              {SYMPTOM_OPTIONS.map((s) => (
                <label key={s} className="flex items-center gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.symptom_types.includes(s)}
                    onChange={() => toggleSymptom(s)}
                    className="rounded accent-field"
                  />
                  {lang === 'es' ? {
                    Cupping: 'Enroscamiento',
                    Strapping: 'Estrechamiento',
                    Stunting: 'Atrofia',
                    Discoloration: 'Decoloración',
                    Other: 'Otro',
                  }[s] : s}
                </label>
              ))}
            </div>
            <FieldError msg={errs.symptoms} />
          </div>

          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Descripción de síntomas' : 'Symptom description'}
            </label>
            <textarea
              rows={4}
              value={form.symptoms_description}
              onChange={(e) => set('symptoms_description', e.target.value)}
              placeholder={lang === 'es'
                ? 'Describa los síntomas observados en detalle...'
                : 'Describe the symptoms you observed in detail...'}
              className={`${INPUT_CLS} resize-none`}
            />
          </div>

          <div className="bg-amber-50 rounded-xl p-4 text-sm text-amber-800 dark:bg-hc-bg dark:text-hc-fg">
            {lang === 'es'
              ? 'Las condiciones meteorológicas (viento, temperatura) se agregarán automáticamente al enviar mediante datos históricos de NOAA.'
              : 'Weather conditions (wind, temperature) will be auto-filled on submit using NOAA historical data.'}
          </div>
        </div>
      )}

      {/* Step 3 */}
      {step === 3 && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {lang === 'es' ? 'Aplicador sospechoso (opcional)' : 'Suspected applicator (optional)'}
            </label>
            <input
              type="text"
              value={form.neighboring_applicator}
              onChange={(e) => set('neighboring_applicator', e.target.value)}
              placeholder={lang === 'es' ? 'Nombre del agricultor/empresa...' : 'Farmer or company name...'}
              className={INPUT_CLS}
            />
          </div>

          <div>
            <p className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-2">
              {lang === 'es' ? 'Lista de documentación fotográfica (recordatorio)' : 'Photo documentation checklist (reminder)'}
            </p>
            {[
              ['photos_field', lang === 'es' ? 'Fotografías del daño en el campo tomadas' : 'Field damage photographs taken'],
              ['photos_gps', lang === 'es' ? 'Fotos con GPS del área afectada' : 'GPS-tagged photos of affected area'],
              ['photos_records', lang === 'es' ? 'Registros de aplicación solicitados' : 'Spray application records requested'],
            ].map(([field, label]) => (
              <label key={field} className="flex items-center gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer mb-1">
                <input
                  type="checkbox"
                  checked={form[field]}
                  onChange={(e) => set(field, e.target.checked)}
                  className="rounded accent-field"
                />
                {label}
              </label>
            ))}
          </div>

          <label className="flex items-center gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer">
            <input
              type="checkbox"
              checked={form.aspb_submitted}
              onChange={(e) => set('aspb_submitted', e.target.checked)}
              className="rounded accent-field"
            />
            {lang === 'es'
              ? 'Ya envié esta queja al ASPB'
              : 'I have already submitted this complaint to ASPB'}
          </label>
        </div>
      )}

      {/* Navigation */}
      <div className="flex gap-3 mt-8">
        {step > 1 && (
          <button
            type="button"
            onClick={() => { setErrs({}); setStep((s) => s - 1) }}
            className={BTN_GHOST_CLS}
          >
            {lang === 'es' ? 'Atrás' : 'Back'}
          </button>
        )}
        {step < TOTAL_STEPS ? (
          <button type="button" onClick={handleNext} className={BTN_PRIMARY_CLS}>
            {lang === 'es' ? 'Siguiente' : 'Next'}
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading}
            className={BTN_PRIMARY_CLS}
          >
            {loading
              ? (lang === 'es' ? 'Enviando...' : 'Submitting...')
              : (lang === 'es' ? 'Enviar reporte' : 'Submit report')}
          </button>
        )}
      </div>
    </div>
  )
}
